/* global Asyncify, HEAPU8, LibraryManager, UTF8ToString, _malloc, mergeInto, setValue */

mergeInto(LibraryManager.library, {
  $LmdjOpfs: {
    root: null,
    leases: new Map(),
    nextLease: 1,

  async workspace() {
    if (!this.root) {
      this.root = await navigator.storage.getDirectory();
    }
    return this.root;
  },

  parts(pointer, length) {
    const normalized = UTF8ToString(pointer, length).replaceAll("\\", "/");
    const clean = normalized.split("/").filter((part) => part && part !== ".");
    if (clean.some((part) => part === "..")) throw new DOMException("", "InvalidStateError");
    return clean[0] === "lmdj-workspace" ? clean.slice(1) : clean;
  },

  async directory(parts, create) {
    let directory = await this.workspace();
    for (const part of parts) {
      directory = await directory.getDirectoryHandle(part, {create});
    }
    return directory;
  },

  async parent(parts, create) {
    if (parts.length === 0) throw new DOMException("", "InvalidStateError");
    return [await this.directory(parts.slice(0, -1), create), parts.at(-1)];
  },

  status(error) {
    const table = Object.freeze({
      NotFoundError: -2,
      NoModificationAllowedError: -7,
      QuotaExceededError: -6,
      InvalidStateError: -5,
    });
    return error instanceof DOMException ? (table[error.name] ?? -1) : -1;
  },

  bytes(pointer, length) {
    return HEAPU8.slice(pointer, pointer + length);
  },

  async digest(value) {
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
    return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  },

  compareUtf8(left, right) {
    const encoder = new TextEncoder();
    const a = encoder.encode(left);
    const b = encoder.encode(right);
    const count = Math.min(a.length, b.length);
    for (let index = 0; index < count; ++index) {
      if (a[index] !== b[index]) return a[index] - b[index];
    }
    return a.length - b.length;
  },

  async replaceComplete(path, length, data, dataLength, observer) {
    const parts = this.parts(path, length);
    const fault = observer ? await observer.replacementFault(parts) : null;
    if (observer) await observer.stopAtFault(fault, "before_write");
    const [parent, name] = await this.parent(parts, false);
    const file = await parent.getFileHandle(name, {create: true});
    const writable = await file.createWritable({keepExistingData: false});
    try {
      const replacement = this.bytes(data, dataLength);
      if (fault === "during_write") {
        await writable.write(replacement.subarray(0, Math.max(1, replacement.length >> 1)));
        await observer.stopAtFault(fault, "during_write");
      } else {
        await writable.write(replacement);
      }
      if (observer) await observer.stopAtFault(fault, "before_close");
      await writable.close();
      if (observer) {
        await observer.stopAtFault(fault, "after_close");
        await observer.stopAtFault(fault, "before_cleanup");
      }
    } catch (error) {
      await writable.abort().catch(() => {});
      throw error;
    }
  },

  async appendDurable(path, length, prefix, data, dataLength, observer) {
    const [parent, name] = await this.parent(this.parts(path, length), false);
    const file = await parent.getFileHandle(name);
    const access = await file.createSyncAccessHandle();
    try {
      const current = access.getSize();
      if (!Number.isSafeInteger(prefix) || prefix < 0 || prefix > current) return -5;
      if (prefix !== current) access.truncate(prefix);
      const bytes = this.bytes(data, dataLength);
      let offset = 0;
      while (offset < bytes.length) {
        const written = access.write(bytes.subarray(offset), {at: prefix + offset});
        if (written <= 0) throw new DOMException("", "InvalidStateError");
        offset += written;
      }
      access.flush();
      if (observer) observer.afterAppendFlush();
    } finally { access.close(); }
    return 0;
  },

  },
  $LmdjOpfsTest__deps: ["$LmdjOpfs"],
  $LmdjOpfsTest: {
    appendFlushes: 0,
    async replacementFault(parts) {
      if (parts.at(-1) !== "manifest.json") return null;
      try {
        const host = await LmdjOpfs.directory([".lmdj-host"], false);
        const file = await (await host.getFileHandle("test-fault.json")).getFile();
        const fault = JSON.parse(await file.text());
        return parts.includes(fault.bundle) ? fault.point : null;
      } catch (_) { return null; }
    },
    async stopAtFault(point, phase) {
      if (point !== phase) return;
      const host = await LmdjOpfs.directory([".lmdj-host"], true);
      const marker = await host.getFileHandle("test-fault-reached", {create: true});
      const writable = await marker.createWritable({keepExistingData: false});
      await writable.write(phase);
      await writable.close();
      await new Promise(() => {});
    },
    afterAppendFlush() { this.appendFlushes += 1; },
  },
  lmdj_opfs_acquire_writer__deps: ["$LmdjOpfs"],
  lmdj_opfs_acquire_writer: (path, length) => Asyncify.handleAsync(async () => {
    try {
      const parts = LmdjOpfs.parts(path, length);
      const normalized = `/lmdj-workspace/${parts.join("/")}`;
      const leases = await LmdjOpfs.directory([".lmdj-host", "leases"], true);
      const name = `${await LmdjOpfs.digest(normalized)}.lock`;
      const file = await leases.getFileHandle(name, {create: true});
      const access = await file.createSyncAccessHandle();
      if (access.getSize() === 0) {
        const identity = crypto.getRandomValues(new Uint8Array(32));
        access.write(identity, {at: 0});
        access.flush();
      }
      const lease = LmdjOpfs.nextLease++;
      LmdjOpfs.leases.set(lease, access);
      return lease;
    } catch (error) {
      const status = LmdjOpfs.status(error);
      return status === -7 ? -3 : status;
    }
  }),

  lmdj_opfs_release_writer__deps: ["$LmdjOpfs"],
  lmdj_opfs_release_writer: (lease) => {
    const access = LmdjOpfs.leases.get(lease);
    if (access) {
      access.close();
      LmdjOpfs.leases.delete(lease);
    }
  },

  lmdj_opfs_ensure_directory__deps: ["$LmdjOpfs"],
  lmdj_opfs_ensure_directory: (path, length) => Asyncify.handleAsync(async () => {
    try {
      await LmdjOpfs.directory(LmdjOpfs.parts(path, length), true);
      return 0;
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_exists__deps: ["$LmdjOpfs"],
  lmdj_opfs_exists: (path, length) => Asyncify.handleAsync(async () => {
    try {
      const parts = LmdjOpfs.parts(path, length);
      if (parts.length === 0) return 1;
      const [parent, name] = await LmdjOpfs.parent(parts, false);
      for await (const entry of parent.values()) if (entry.name === name) return 1;
      return 0;
    } catch (error) {
      return error instanceof DOMException && error.name === "NotFoundError" ? 0 : LmdjOpfs.status(error);
    }
  }),

  lmdj_opfs_byte_length__deps: ["$LmdjOpfs"],
  lmdj_opfs_byte_length: (path, length) => Asyncify.handleAsync(async () => {
    try {
      const parts = LmdjOpfs.parts(path, length);
      const [parent, name] = await LmdjOpfs.parent(parts, false);
      const file = await (await parent.getFileHandle(name)).getFile();
      return file.size;
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_read_complete__deps: ["$LmdjOpfs"],
  lmdj_opfs_read_complete: (path, length, output, outputLength) => Asyncify.handleAsync(async () => {
    try {
      const [parent, name] = await LmdjOpfs.parent(LmdjOpfs.parts(path, length), false);
      const bytes = new Uint8Array(await (await (await parent.getFileHandle(name)).getFile()).arrayBuffer());
      const allocation = _malloc(bytes.length || 1);
      HEAPU8.set(bytes, allocation);
      setValue(output, allocation, "*");
      setValue(outputLength, bytes.length, "i32");
      return 0;
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_create_immutable__deps: ["$LmdjOpfs"],
  lmdj_opfs_create_immutable: (path, length, data, dataLength) => Asyncify.handleAsync(async () => {
    try {
      const [parent, name] = await LmdjOpfs.parent(LmdjOpfs.parts(path, length), false);
      for await (const entry of parent.values()) if (entry.name === name) return -4;
      const file = await parent.getFileHandle(name, {create: true});
      const access = await file.createSyncAccessHandle();
      try {
        access.truncate(0);
        access.write(LmdjOpfs.bytes(data, dataLength), {at: 0});
        access.flush();
      } finally { access.close(); }
      return 0;
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_replace_complete__deps: ["$LmdjOpfs"],
  lmdj_opfs_replace_complete: (path, length, data, dataLength) => Asyncify.handleAsync(async () => {
    try {
      await LmdjOpfs.replaceComplete(path, length, data, dataLength, null);
      return 0;
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_replace_complete_test__deps: ["$LmdjOpfs", "$LmdjOpfsTest"],
  lmdj_opfs_replace_complete_test: (path, length, data, dataLength) => Asyncify.handleAsync(async () => {
    try {
      await LmdjOpfs.replaceComplete(path, length, data, dataLength, LmdjOpfsTest);
      return 0;
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_append_durable__deps: ["$LmdjOpfs"],
  lmdj_opfs_append_durable: (path, length, prefix, data, dataLength) => Asyncify.handleAsync(async () => {
    try {
      return await LmdjOpfs.appendDurable(path, length, prefix, data, dataLength, null);
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_append_durable_test__deps: ["$LmdjOpfs", "$LmdjOpfsTest"],
  lmdj_opfs_append_durable_test: (path, length, prefix, data, dataLength) => Asyncify.handleAsync(async () => {
    try {
      return await LmdjOpfs.appendDurable(
          path, length, prefix, data, dataLength, LmdjOpfsTest);
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_append_flush_count__deps: ["$LmdjOpfsTest"],
  lmdj_opfs_append_flush_count: () => LmdjOpfsTest.appendFlushes,

  lmdj_opfs_remove__deps: ["$LmdjOpfs"],
  lmdj_opfs_remove: (path, length) => Asyncify.handleAsync(async () => {
    try {
      const [parent, name] = await LmdjOpfs.parent(LmdjOpfs.parts(path, length), false);
      await parent.removeEntry(name);
      return 0;
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_list_names__deps: ["$LmdjOpfs"],
  lmdj_opfs_list_names: (path, length, output, outputLength) => Asyncify.handleAsync(async () => {
    try {
      const directory = await LmdjOpfs.directory(LmdjOpfs.parts(path, length), false);
      const names = [];
      for await (const entry of directory.values()) if (entry.kind === "file") names.push(entry.name);
      names.sort((a, b) => LmdjOpfs.compareUtf8(a, b));
      const encoder = new TextEncoder();
      const encoded = names.map((name) => encoder.encode(`${name}\0`));
      const total = encoded.reduce((sum, bytes) => sum + bytes.length, 0);
      const allocation = _malloc(total || 1);
      let cursor = allocation;
      for (const bytes of encoded) { HEAPU8.set(bytes, cursor); cursor += bytes.length; }
      setValue(output, allocation, "*");
      setValue(outputLength, total, "i32");
      return 0;
    } catch (error) { return LmdjOpfs.status(error); }
  }),

  lmdj_opfs_validate_tree__deps: ["$LmdjOpfs"],
  lmdj_opfs_validate_tree: (path, length) => Asyncify.handleAsync(async () => {
    try {
      const parts = LmdjOpfs.parts(path, length);
      if (parts.length === 0) return 0;
      const [parent, name] = await LmdjOpfs.parent(parts, false);
      for await (const entry of parent.values()) if (entry.name === name) return 0;
      return 0;
    } catch (error) {
      return error instanceof DOMException && error.name === "NotFoundError" ? 0 : LmdjOpfs.status(error);
    }
  }),
});
