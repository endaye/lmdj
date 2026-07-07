import { useRef, useState } from "react";

const ASCII = String.raw`
   ┌───────────────────────────────┐
   │  drop a patch package here    │
   │  (folder with patch.json)     │
   └───────────────────────────────┘`;

/** 目录选择器：webkitRelativePath 形如 "pkgdir/patch.json" → 去掉首段得包相对路径 */
export async function readPickedFiles(list: FileList): Promise<Map<string, ArrayBuffer>> {
  const files = new Map<string, ArrayBuffer>();
  for (const file of Array.from(list)) {
    const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    const path = rel.includes("/") ? rel.split("/").slice(1).join("/") : rel;
    files.set(path, await file.arrayBuffer());
  }
  return files;
}

/** 拖放目录：webkitGetAsEntry 递归遍历（readEntries 需循环取批次） */
export async function readDroppedItems(
  items: DataTransferItemList,
): Promise<Map<string, ArrayBuffer>> {
  const files = new Map<string, ArrayBuffer>();

  async function allEntries(dir: FileSystemDirectoryEntry): Promise<FileSystemEntry[]> {
    const reader = dir.createReader();
    const out: FileSystemEntry[] = [];
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((res, rej) =>
        reader.readEntries(res, rej),
      );
      if (batch.length === 0) return out;
      out.push(...batch);
    }
  }

  async function walk(entry: FileSystemEntry, path: string): Promise<void> {
    if (entry.isFile) {
      const file = await new Promise<File>((res, rej) =>
        (entry as FileSystemFileEntry).file(res, rej),
      );
      files.set(path, await file.arrayBuffer());
    } else if (entry.isDirectory) {
      for (const child of await allEntries(entry as FileSystemDirectoryEntry)) {
        await walk(child, path ? `${path}/${child.name}` : child.name);
      }
    }
  }

  for (const item of Array.from(items)) {
    const entry = item.webkitGetAsEntry?.();
    if (entry?.isDirectory) await walk(entry, ""); // 顶层目录名不入包相对路径
    else if (entry) await walk(entry, entry.name);
  }
  return files;
}

export function DropZone({
  onFiles,
  onExample,
}: {
  onFiles: (files: Map<string, ArrayBuffer>) => void;
  onExample: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <div
      className={`drop-zone${over ? " drop-zone--over" : ""}`}
      data-testid="drop-zone"
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        void readDroppedItems(e.dataTransfer.items).then(onFiles);
      }}
    >
      <div>{ASCII}</div>
      <p>
        <button onClick={() => inputRef.current?.click()}>选择 package 目录</button>{" "}
        <button onClick={onExample}>加载示例 patch</button>
      </p>
      <input
        ref={inputRef}
        type="file"
        style={{ display: "none" }}
        // @ts-expect-error 非标准属性，主流浏览器均支持
        webkitdirectory=""
        multiple
        onChange={(e) => {
          if (e.target.files) void readPickedFiles(e.target.files).then(onFiles);
        }}
      />
    </div>
  );
}
