"""作ったグラデーションとパレットの保存先(ctx.data_dir の library.json)。Qt にも Graphica 本体にも依存しない。

プラグインの保存先はタブごとではなく1つなので、同じファイルを指す Library はプロセスに1つにして
(get_library)、変更を全タブのパネルとウィンドウに知らせる。別の Graphica が同じファイルを
書き換えた場合に備え、読むたびに更新時刻を見て読み直す。
"""
import datetime
import json
import os
import tempfile
import uuid
import weakref

from . import colors as C

FORMAT = "graphica-color-studio"
FORMAT_VERSION = 1
FILENAME = "library.json"
KINDS = ("gradient", "palette")
KIND_LABELS = {"gradient": "グラデーション", "palette": "配色パレット"}
MAX_NAME_LENGTH = 60
MAX_COLORS = 64


class LibraryError(ValueError):
    """メッセージはそのまま利用者に表示する。"""


class NewerLibraryError(LibraryError):
    """新しい版のプラグインが書いたファイル。壊れたものとして退避してはいけない。"""


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_name(name):
    if not isinstance(name, str) or not name.strip():
        raise LibraryError("名前を入力してください。")
    name = " ".join(name.split())
    if len(name) > MAX_NAME_LENGTH:
        raise LibraryError(f"名前が長すぎます({MAX_NAME_LENGTH}文字まで)。")
    return name


def unique_name(name, taken):
    """taken に無ければそのまま、あれば「名前 (2)」「名前 (3)」…。"""
    taken = set(taken)
    if name not in taken:
        return name
    n = 2
    while f"{name} ({n})" in taken:
        n += 1
    return f"{name} ({n})"


def _validate_entry(raw):
    if not isinstance(raw, dict):
        raise LibraryError("項目の形が正しくありません。")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise LibraryError(f"未知の種類です: {kind!r}")
    colors = raw.get("colors")
    if not isinstance(colors, list) or not 1 <= len(colors) <= MAX_COLORS:
        raise LibraryError("色の一覧が正しくありません。")
    source = raw.get("source") or {}
    if not isinstance(source, dict):
        raise LibraryError("作り方のデータが正しくありません。")
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex),
        "kind": kind,
        "name": normalize_name(raw.get("name")),
        "colors": [C.normalize_hex(c) for c in colors],
        "source": source,
        "created": str(raw.get("created") or _now()),
        "updated": str(raw.get("updated") or raw.get("created") or _now()),
    }


def _parse_document(data):
    """(妥当な項目のリスト, 捨てた項目の数)。"""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise LibraryError("カラースタジオのライブラリのファイルではありません。")
    version = data.get("version")
    if not isinstance(version, int) or version > FORMAT_VERSION:
        raise NewerLibraryError("新しい版のカラースタジオで作られたファイルです。プラグインを更新してください。")
    entries, dropped = [], 0
    for raw in data.get("entries") or []:
        try:
            entries.append(_validate_entry(raw))
        except (LibraryError, C.ColorError):
            dropped += 1
    return entries, dropped


def _document(entries):
    return {"format": FORMAT, "version": FORMAT_VERSION, "entries": entries}


def _write_json_atomically(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".library-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


class Library:
    def __init__(self, path):
        self.path = path
        self._entries = []
        self._mtime = None
        self._listeners = []
        # 読めなかったファイルを退避した先と、捨てた項目の数。UI が一度だけ利用者に知らせる。
        self.recovered_to = None
        self.dropped_count = 0
        self._load()

    # --- 読み書き ---

    def _file_mtime(self):
        try:
            return os.stat(self.path).st_mtime_ns
        except OSError:
            return None

    def _load(self):
        self._mtime = self._file_mtime()
        if self._mtime is None:
            self._entries = []
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            raise LibraryError(f"ライブラリを読めません: {e}") from e
        try:
            self._entries, self.dropped_count = _parse_document(json.loads(text))
        except NewerLibraryError:
            raise
        except ValueError:
            # 中身が壊れたファイルは消さずに退避し、空のライブラリで続ける。
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = f"{self.path}.broken-{stamp}"
            try:
                os.replace(self.path, backup)
                self.recovered_to = backup
            except OSError:
                self.recovered_to = None
            self._entries = []
            self._mtime = self._file_mtime()

    def _refresh(self):
        if self._file_mtime() != self._mtime:
            self._load()

    def _save(self):
        _write_json_atomically(self.path, _document(self._entries))
        self._mtime = self._file_mtime()
        self._notify()

    # --- 変更の通知 ---

    def add_listener(self, callback):
        """callback() を変更のたびに呼ぶ。束縛メソッドは弱参照で持つので、閉じたウィジェットは自然に外れる。"""
        ref = weakref.WeakMethod(callback) if hasattr(callback, "__self__") else (lambda cb=callback: cb)
        self._listeners.append(ref)

    def remove_listener(self, callback):
        self._listeners = [r for r in self._listeners if r() is not None and r() != callback]

    def _notify(self):
        alive = []
        for ref in self._listeners:
            cb = ref()
            if cb is None:
                continue
            try:
                cb()
            except RuntimeError:
                # 破棄済みの Qt ウィジェット。以後は呼ばない。
                continue
            alive.append(ref)
        self._listeners = alive

    # --- 操作 ---

    def entries(self, kind=None):
        self._refresh()
        return [dict(e) for e in self._entries if kind is None or e["kind"] == kind]

    def get(self, entry_id):
        self._refresh()
        for e in self._entries:
            if e["id"] == entry_id:
                return dict(e)
        raise LibraryError("その項目はライブラリにありません(ほかの画面で削除された可能性があります)。")

    def names(self):
        return [e["name"] for e in self.entries()]

    def find_by_name(self, name):
        for e in self.entries():
            if e["name"] == name:
                return e
        return None

    def add(self, kind, name, colors, source=None, *, replace_id=None):
        """
        項目を足す。replace_id を渡すと、その項目を置き換える(同名で上書き保存するとき)。

        Returns:
            dict: 保存した項目。
        """
        self._refresh()
        entry = _validate_entry({"kind": kind, "name": name, "colors": list(colors), "source": source or {}})
        if replace_id is not None:
            for i, e in enumerate(self._entries):
                if e["id"] == replace_id:
                    entry["id"], entry["created"] = e["id"], e["created"]
                    self._entries[i] = entry
                    break
            else:
                raise LibraryError("上書きする項目が見つかりません。")
        else:
            if entry["name"] in {e["name"] for e in self._entries}:
                raise LibraryError(f"「{entry['name']}」は既にあります。別の名前にするか、上書きしてください。")
            self._entries.append(entry)
        self._save()
        return dict(entry)

    def rename(self, entry_id, name):
        self._refresh()
        name = normalize_name(name)
        if any(e["name"] == name and e["id"] != entry_id for e in self._entries):
            raise LibraryError(f"「{name}」は既にあります。")
        self._entry_ref(entry_id).update(name=name, updated=_now())
        self._save()

    def duplicate(self, entry_id):
        self._refresh()
        src = self._entry_ref(entry_id)
        copy = dict(src, id=uuid.uuid4().hex, created=_now(), updated=_now(),
                    name=unique_name(f"{src['name']} のコピー", {e["name"] for e in self._entries}))
        copy["name"] = copy["name"][:MAX_NAME_LENGTH]
        self._entries.append(copy)
        self._save()
        return dict(copy)

    def delete(self, entry_id):
        self._refresh()
        self._entry_ref(entry_id)
        self._entries = [e for e in self._entries if e["id"] != entry_id]
        self._save()

    def move(self, entry_id, offset):
        self._refresh()
        i = next(k for k, e in enumerate(self._entries) if e["id"] == self._entry_ref(entry_id)["id"])
        j = min(max(i + offset, 0), len(self._entries) - 1)
        if i != j:
            self._entries.insert(j, self._entries.pop(i))
            self._save()

    def _entry_ref(self, entry_id):
        for e in self._entries:
            if e["id"] == entry_id:
                return e
        raise LibraryError("その項目はライブラリにありません(ほかの画面で削除された可能性があります)。")

    # --- 書き出し / 読み込み ---

    def export(self, entry_ids, path):
        self._refresh()
        wanted = set(entry_ids)
        entries = [e for e in self._entries if e["id"] in wanted]
        if not entries:
            raise LibraryError("書き出す項目を選んでください。")
        _write_json_atomically(path, _document(entries))
        return len(entries)

    def import_file(self, path):
        """
        Returns:
            tuple[list[dict], int]: 追加した項目と、読めずに捨てた項目の数。同名は「名前 (2)」にして足す。
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except OSError as e:
            raise LibraryError(f"ファイルを開けません: {e}") from e
        except ValueError as e:
            raise LibraryError("JSON として読めません。") from e
        incoming, dropped = _parse_document(data)
        self._refresh()
        taken = {e["name"] for e in self._entries}
        added = []
        for e in incoming:
            name = unique_name(e["name"], taken)[:MAX_NAME_LENGTH]
            taken.add(name)
            entry = dict(e, id=uuid.uuid4().hex, name=name)
            self._entries.append(entry)
            added.append(dict(entry))
        if added:
            self._save()
        return added, dropped


_LIBRARIES = {}


def get_library(data_dir):
    path = os.path.normcase(os.path.abspath(os.path.join(data_dir, FILENAME)))
    lib = _LIBRARIES.get(path)
    if lib is None:
        lib = _LIBRARIES[path] = Library(os.path.join(data_dir, FILENAME))
    return lib
