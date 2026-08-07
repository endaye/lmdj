/* global Asyncify, HEAPU8, LibraryManager, UTF8ToString, _malloc, mergeInto, setValue */

mergeInto(LibraryManager.library, {
  $LmdjOpfs: {
    root: null,
    leaseTokens: new Map(),
    leasesByPath: new Map(),
    nextLeaseToken: 1,

    async workspace() {
      if (!this.root) this.root = await navigator.storage.getDirectory();
      return this.root;
    },

    parts(pointer, length) {
      return this.pathParts(UTF8ToString(pointer, length));
    },

    pathParts(input) {
      const clean = input.replaceAll("\\", "/")
          .split("/")
          .filter((part) => part && part !== ".");
      if (clean.some((part) => part === "..")) {
        throw new DOMException("", "InvalidStateError");
      }
      return clean[0] === "lmdj-workspace" ? clean.slice(1) : clean;
    },

    canonicalPath(parts) {
      return `/lmdj-workspace/${parts.join("/")}`;
    },

    async directory(parts, create) {
      let directory = await this.workspace();
      for (const part of parts) {
        directory = await directory.getDirectoryHandle(part, {create});
      }
      return directory;
    },

    async parent(parts, create) {
      if (parts.length === 0) {
        throw new DOMException("", "InvalidStateError");
      }
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

    isMissingEntry(error) {
      return error instanceof DOMException &&
          (error.name === "NotFoundError" || error.name === "TypeMismatchError");
    },

    async exists(parts) {
      if (parts.length === 0) {
        await this.workspace();
        return true;
      }
      try {
        const [parent, name] = await this.parent(parts, false);
        try {
          await parent.getFileHandle(name);
          return true;
        } catch (error) {
          if (!this.isMissingEntry(error)) throw error;
        }
        try {
          await parent.getDirectoryHandle(name);
          return true;
        } catch (error) {
          if (!this.isMissingEntry(error)) throw error;
        }
        return false;
      } catch (error) {
        if (this.isMissingEntry(error)) return false;
        throw error;
      }
    },

    async directoryExists(parts) {
      try {
        await this.directory(parts, false);
        return true;
      } catch (error) {
        if (this.isMissingEntry(error)) return false;
        throw error;
      }
    },

    async listEntries(parts, kind) {
      const directory = await this.directory(parts, false);
      const names = [];
      for await (const entry of directory.values()) {
        if (entry.kind === kind) names.push(entry.name);
      }
      names.sort((a, b) => this.compareUtf8(a, b));
      return names;
    },

    writeNames(names, output, outputLength) {
      const encoder = new TextEncoder();
      const encoded = names.map((name) => encoder.encode(`${name}\0`));
      const total = encoded.reduce((sum, bytes) => sum + bytes.length, 0);
      const allocation = _malloc(total || 1);
      let cursor = allocation;
      for (const bytes of encoded) {
        HEAPU8.set(bytes, cursor);
        cursor += bytes.length;
      }
      setValue(output, allocation, "*");
      setValue(outputLength, total, "i32");
    },

    bytes(pointer, length) {
      return HEAPU8.slice(pointer, pointer + length);
    },

    async sha256(bytes) {
      const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
      return [...digest]
          .map((byte) => byte.toString(16).padStart(2, "0"))
          .join("");
    },

    async pathKey(value) {
      return this.sha256(new TextEncoder().encode(value));
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

    async readFileBytes(fileHandle) {
      return new Uint8Array(await (await fileHandle.getFile()).arrayBuffer());
    },

    async fileState(parts) {
      try {
        const [parent, name] = await this.parent(parts, false);
        const handle = await parent.getFileHandle(name);
        const bytes = await this.readFileBytes(handle);
        return {
          state: "existing",
          length: bytes.length,
          sha256: await this.sha256(bytes),
        };
      } catch (error) {
        if (error instanceof DOMException && error.name === "NotFoundError") {
          return {state: "absent"};
        }
        throw error;
      }
    },

    stateMatches(actual, expected) {
      if (actual.state !== expected.state) return false;
      return actual.state === "absent" ||
          (actual.length === expected.length && actual.sha256 === expected.sha256);
    },

    async writeSyncComplete(fileHandle, bytes, observer, operation, fault = null) {
      const access = await fileHandle.createSyncAccessHandle();
      try {
        access.truncate(0);
        let offset = 0;
        while (offset < bytes.length) {
          const requested = observer
            ? observer.writeChunkSize(operation, bytes.length - offset)
            : bytes.length - offset;
          const written = access.write(
              bytes.subarray(offset, offset + requested), {at: offset});
          if (!Number.isSafeInteger(written) || written <= 0) {
            throw new DOMException("", "InvalidStateError");
          }
          offset += written;
          if (observer) await observer.afterWrite(operation, offset);
          if (observer) await observer.stopAtFault(fault, "during_write");
        }
        if (access.getSize() !== bytes.length) {
          throw new DOMException("", "InvalidStateError");
        }
        const verified = new Uint8Array(bytes.length);
        let readOffset = 0;
        while (readOffset < verified.length) {
          const read = access.read(verified.subarray(readOffset), {at: readOffset});
          if (!Number.isSafeInteger(read) || read <= 0) {
            throw new DOMException("", "InvalidStateError");
          }
          readOffset += read;
        }
        if (await this.sha256(verified) !== await this.sha256(bytes)) {
          throw new DOMException("", "InvalidStateError");
        }
        access.flush();
        if (observer) observer.afterFlush(operation);
      } finally {
        access.close();
      }
    },

    activeLease(destination) {
      let match = null;
      for (const state of this.leasesByPath.values()) {
        const contained = destination === state.projectPath ||
            destination.startsWith(`${state.projectPath}/`);
        if (contained && (!match || state.projectPath.length > match.projectPath.length)) {
          match = state;
        }
      }
      if (!match) throw new DOMException("", "InvalidStateError");
      return match;
    },

    async intentDirectory(scopeKey, create) {
      try {
        return await this.directory(
            [".lmdj-host", "storage-intents", scopeKey], create);
      } catch (error) {
        if (!create && error instanceof DOMException && error.name === "NotFoundError") {
          return null;
        }
        throw error;
      }
    },

    async createIntent(parts, operation, newBytes) {
      const destination = this.canonicalPath(parts);
      const lease = this.activeLease(destination);
      const directory = await this.intentDirectory(lease.scopeKey, true);
      const name = `${await this.pathKey(destination)}.json`;
      try {
        await directory.getFileHandle(name);
        throw new DOMException("", "InvalidStateError");
      } catch (error) {
        if (!(error instanceof DOMException) || error.name !== "NotFoundError") {
          throw error;
        }
      }
      const previous = await this.fileState(parts);
      const record = {
        contract: "lmdj.storage.intent.v1",
        destination,
        operation,
        next: {sha256: await this.sha256(newBytes), length: newBytes.length},
        previous,
      };
      const encoded = new TextEncoder().encode(JSON.stringify(record));
      const handle = await directory.getFileHandle(name, {create: true});
      await this.writeSyncComplete(handle, encoded, null, "intent");
      const verified = await this.readFileBytes(handle);
      if (verified.length !== encoded.length ||
          await this.sha256(verified) !== await this.sha256(encoded)) {
        throw new DOMException("", "InvalidStateError");
      }
      return {directory, name, record};
    },

    validHash(value) {
      return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
    },

    validateIntent(record, lease) {
      if (!record || record.contract !== "lmdj.storage.intent.v1" ||
          !["replace_complete", "create_immutable"].includes(record.operation) ||
          typeof record.destination !== "string" ||
          !(record.destination === lease.projectPath ||
            record.destination.startsWith(`${lease.projectPath}/`)) ||
          !record.next || !this.validHash(record.next.sha256) ||
          !Number.isSafeInteger(record.next.length) || record.next.length < 0 ||
          !record.previous || !["absent", "existing"].includes(record.previous.state)) {
        throw new DOMException("", "InvalidStateError");
      }
      if (record.previous.state === "existing" &&
          (!this.validHash(record.previous.sha256) ||
           !Number.isSafeInteger(record.previous.length) ||
           record.previous.length < 0)) {
        throw new DOMException("", "InvalidStateError");
      }
    },

    async recoverIntents(lease) {
      const directory = await this.intentDirectory(lease.scopeKey, false);
      if (!directory) return;
      const names = [];
      for await (const entry of directory.values()) {
        if (entry.kind === "file") names.push(entry.name);
      }
      names.sort((a, b) => this.compareUtf8(a, b));
      for (const name of names) {
        const handle = await directory.getFileHandle(name);
        let record;
        try {
          record = JSON.parse(new TextDecoder().decode(await this.readFileBytes(handle)));
        } catch (_) {
          throw new DOMException("", "InvalidStateError");
        }
        this.validateIntent(record, lease);
        if (name !== `${await this.pathKey(record.destination)}.json`) {
          throw new DOMException("", "InvalidStateError");
        }
        const parts = this.pathParts(record.destination);
        const actual = await this.fileState(parts);
        const next = {state: "existing", ...record.next};
        if (this.stateMatches(actual, next) ||
            this.stateMatches(actual, record.previous)) {
          await directory.removeEntry(name);
          continue;
        }
        if (record.previous.state === "absent") {
          const [parent, destinationName] = await this.parent(parts, false);
          await parent.removeEntry(destinationName).catch((error) => {
            if (!(error instanceof DOMException) || error.name !== "NotFoundError") {
              throw error;
            }
          });
          if ((await this.fileState(parts)).state !== "absent") {
            throw new DOMException("", "InvalidStateError");
          }
          await directory.removeEntry(name);
          continue;
        }
        throw new DOMException("", "InvalidStateError");
      }
    },

    newLeaseToken(state) {
      const token = this.nextLeaseToken++;
      state.references += 1;
      this.leaseTokens.set(token, state);
      return token;
    },

    async acquireWriter(path, length, platformIdentity) {
      const projectPath = this.canonicalPath(this.parts(path, length));
      const existing = this.leasesByPath.get(projectPath);
      if (existing) {
        if (existing.platformIdentity !== platformIdentity) {
          throw new DOMException("", "NoModificationAllowedError");
        }
        return this.newLeaseToken(existing);
      }

      const scopeKey = await this.pathKey(projectPath);
      const leases = await this.directory([".lmdj-host", "leases"], true);
      const file = await leases.getFileHandle(`${scopeKey}.lock`, {create: true});
      const access = await file.createSyncAccessHandle();
      try {
        if (access.getSize() === 0) {
          const identity = crypto.getRandomValues(new Uint8Array(32));
          let offset = 0;
          while (offset < identity.length) {
            const written = access.write(identity.subarray(offset), {at: offset});
            if (!Number.isSafeInteger(written) || written <= 0) {
              throw new DOMException("", "InvalidStateError");
            }
            offset += written;
          }
          if (access.getSize() !== identity.length) {
            throw new DOMException("", "InvalidStateError");
          }
          access.flush();
        }
        const state = {
          projectPath,
          scopeKey,
          platformIdentity,
          access,
          references: 0,
        };
        await this.recoverIntents(state);
        this.leasesByPath.set(projectPath, state);
        return this.newLeaseToken(state);
      } catch (error) {
        access.close();
        throw error;
      }
    },

    releaseWriter(token) {
      const state = this.leaseTokens.get(token);
      if (!state) return;
      this.leaseTokens.delete(token);
      state.references -= 1;
      if (state.references === 0) {
        this.leasesByPath.delete(state.projectPath);
        state.access.close();
      }
    },

    releaseAllWriters() {
      const states = new Set(this.leasesByPath.values());
      this.leaseTokens.clear();
      this.leasesByPath.clear();
      for (const state of states) {
        state.references = 0;
        state.access.close();
      }
    },

    async replaceComplete(path, length, data, dataLength, observer) {
      const parts = this.parts(path, length);
      const replacement = this.bytes(data, dataLength);
      const intent = await this.createIntent(parts, "replace_complete", replacement);
      const destination = this.canonicalPath(parts);
      const fault = observer
        ? await observer.faultForDestination(destination)
        : null;
      if (observer) await observer.stopAtFault(fault, "before_write");
      const [parent, name] = await this.parent(parts, false);
      const file = await parent.getFileHandle(name, {create: true});
      const writable = await file.createWritable({keepExistingData: false});
      try {
        if (fault === "during_write") {
          await writable.write(
              replacement.subarray(0, Math.max(1, replacement.length >> 1)));
          await observer.stopAtFault(fault, "during_write");
        } else {
          await writable.write(replacement);
        }
        if (observer) await observer.stopAtFault(fault, "before_close");
        await writable.close();
      } catch (error) {
        await writable.abort().catch(() => {});
        throw error;
      }
      if (observer) await observer.stopAtFault(fault, "after_close");
      const actual = await this.fileState(parts);
      const expected = {state: "existing", ...intent.record.next};
      if (!this.stateMatches(actual, expected)) {
        throw new DOMException("", "InvalidStateError");
      }
      if (observer) await observer.stopAtFault(fault, "before_cleanup");
      await intent.directory.removeEntry(intent.name);
    },

    async createImmutable(path, length, data, dataLength, observer) {
      const parts = this.parts(path, length);
      if ((await this.fileState(parts)).state !== "absent") return -4;
      const payload = this.bytes(data, dataLength);
      const intent = await this.createIntent(parts, "create_immutable", payload);
      const destination = this.canonicalPath(parts);
      const fault = observer
        ? await observer.faultForDestination(destination)
        : null;
      const [parent, name] = await this.parent(parts, false);
      const file = await parent.getFileHandle(name, {create: true});
      await this.writeSyncComplete(
          file, payload, observer, "immutable", fault);
      const actual = await this.fileState(parts);
      const expected = {state: "existing", ...intent.record.next};
      if (!this.stateMatches(actual, expected)) {
        throw new DOMException("", "InvalidStateError");
      }
      await intent.directory.removeEntry(intent.name);
      return 0;
    },

    async appendDurable(path, length, prefix, data, dataLength, observer) {
      const [parent, name] = await this.parent(this.parts(path, length), false);
      const file = await parent.getFileHandle(name);
      const access = await file.createSyncAccessHandle();
      try {
        const current = access.getSize();
        if (!Number.isSafeInteger(prefix) || prefix < 0 || prefix > current) {
          return -5;
        }
        if (prefix !== current) access.truncate(prefix);
        const bytes = this.bytes(data, dataLength);
        let offset = 0;
        while (offset < bytes.length) {
          const written = access.write(bytes.subarray(offset), {at: prefix + offset});
          if (!Number.isSafeInteger(written) || written <= 0) {
            throw new DOMException("", "InvalidStateError");
          }
          offset += written;
        }
        access.flush();
        if (observer) observer.afterFlush("append");
      } finally {
        access.close();
      }
      return 0;
    },
  },

  $LmdjOpfsTest__deps: ["$LmdjOpfs"],
  $LmdjOpfsTest: {
    appendFlushes: 0,
    immutableWrites: 0,

    async faultForDestination(destination) {
      try {
        const host = await LmdjOpfs.directory([".lmdj-host"], false);
        const file = await (await host.getFileHandle("test-fault.json")).getFile();
        const fault = JSON.parse(await file.text());
        return fault.destination === destination ? fault.point : null;
      } catch (_) {
        return null;
      }
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

    writeChunkSize(operation, remaining) {
      return operation === "immutable" ? Math.min(2, remaining) : remaining;
    },

    async afterWrite(operation) {
      if (operation === "immutable") this.immutableWrites += 1;
    },

    afterFlush(operation) {
      if (operation === "append") this.appendFlushes += 1;
    },
  },

  lmdj_opfs_acquire_writer__deps: ["$LmdjOpfs"],
  lmdj_opfs_acquire_writer: (path, length, platformIdentity) => Asyncify.handleAsync(async () => {
    try {
      return await LmdjOpfs.acquireWriter(path, length, platformIdentity);
    } catch (error) {
      const status = LmdjOpfs.status(error);
      return status === -7 ? -3 : status;
    }
  }),

  lmdj_opfs_release_writer__deps: ["$LmdjOpfs"],
  lmdj_opfs_release_writer: (token) => LmdjOpfs.releaseWriter(token),

  lmdj_opfs_ensure_directory__deps: ["$LmdjOpfs"],
  lmdj_opfs_ensure_directory: (path, length) => Asyncify.handleAsync(async () => {
    try {
      await LmdjOpfs.directory(LmdjOpfs.parts(path, length), true);
      return 0;
    } catch (error) {
      return LmdjOpfs.status(error);
    }
  }),

  lmdj_opfs_exists__deps: ["$LmdjOpfs"],
  lmdj_opfs_exists: (path, length) => Asyncify.handleAsync(async () => {
    try {
      return await LmdjOpfs.exists(LmdjOpfs.parts(path, length)) ? 1 : 0;
    } catch (error) {
      return LmdjOpfs.status(error);
    }
  }),

  lmdj_opfs_directory_exists__deps: ["$LmdjOpfs"],
  lmdj_opfs_directory_exists:
      (path, length) => Asyncify.handleAsync(async () => {
        try {
          return await LmdjOpfs.directoryExists(
              LmdjOpfs.parts(path, length)) ? 1 : 0;
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_byte_length__deps: ["$LmdjOpfs"],
  lmdj_opfs_byte_length: (path, length) => Asyncify.handleAsync(async () => {
    try {
      const [parent, name] = await LmdjOpfs.parent(
          LmdjOpfs.parts(path, length), false);
      return (await (await parent.getFileHandle(name)).getFile()).size;
    } catch (error) {
      return LmdjOpfs.status(error);
    }
  }),

  lmdj_opfs_read_complete__deps: ["$LmdjOpfs"],
  lmdj_opfs_read_complete:
      (path, length, output, outputLength) => Asyncify.handleAsync(async () => {
        try {
          const [parent, name] = await LmdjOpfs.parent(
              LmdjOpfs.parts(path, length), false);
          const bytes = await LmdjOpfs.readFileBytes(
              await parent.getFileHandle(name));
          const allocation = _malloc(bytes.length || 1);
          HEAPU8.set(bytes, allocation);
          setValue(output, allocation, "*");
          setValue(outputLength, bytes.length, "i32");
          return 0;
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_create_immutable__deps: ["$LmdjOpfs"],
  lmdj_opfs_create_immutable:
      (path, length, data, dataLength) => Asyncify.handleAsync(async () => {
        try {
          return await LmdjOpfs.createImmutable(
              path, length, data, dataLength, null);
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_create_immutable_test__deps: ["$LmdjOpfs", "$LmdjOpfsTest"],
  lmdj_opfs_create_immutable_test:
      (path, length, data, dataLength) => Asyncify.handleAsync(async () => {
        try {
          return await LmdjOpfs.createImmutable(
              path, length, data, dataLength, LmdjOpfsTest);
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_replace_complete__deps: ["$LmdjOpfs"],
  lmdj_opfs_replace_complete:
      (path, length, data, dataLength) => Asyncify.handleAsync(async () => {
        try {
          await LmdjOpfs.replaceComplete(path, length, data, dataLength, null);
          return 0;
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_replace_complete_test__deps: ["$LmdjOpfs", "$LmdjOpfsTest"],
  lmdj_opfs_replace_complete_test:
      (path, length, data, dataLength) => Asyncify.handleAsync(async () => {
        try {
          await LmdjOpfs.replaceComplete(
              path, length, data, dataLength, LmdjOpfsTest);
          return 0;
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_append_durable__deps: ["$LmdjOpfs"],
  lmdj_opfs_append_durable:
      (path, length, prefix, data, dataLength) => Asyncify.handleAsync(async () => {
        try {
          return await LmdjOpfs.appendDurable(
              path, length, prefix, data, dataLength, null);
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_append_durable_test__deps: ["$LmdjOpfs", "$LmdjOpfsTest"],
  lmdj_opfs_append_durable_test:
      (path, length, prefix, data, dataLength) => Asyncify.handleAsync(async () => {
        try {
          return await LmdjOpfs.appendDurable(
              path, length, prefix, data, dataLength, LmdjOpfsTest);
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_append_flush_count__deps: ["$LmdjOpfsTest"],
  lmdj_opfs_append_flush_count: () => LmdjOpfsTest.appendFlushes,

  lmdj_opfs_immutable_write_count__deps: ["$LmdjOpfsTest"],
  lmdj_opfs_immutable_write_count: () => LmdjOpfsTest.immutableWrites,

  lmdj_opfs_remove__deps: ["$LmdjOpfs"],
  lmdj_opfs_remove: (path, length) => Asyncify.handleAsync(async () => {
    try {
      const [parent, name] = await LmdjOpfs.parent(
          LmdjOpfs.parts(path, length), false);
      await parent.removeEntry(name).catch((error) => {
        if (!(error instanceof DOMException) || error.name !== "NotFoundError") {
          throw error;
        }
      });
      return 0;
    } catch (error) {
      return error instanceof DOMException && error.name === "NotFoundError"
        ? 0
        : LmdjOpfs.status(error);
    }
  }),

  lmdj_opfs_list_names__deps: ["$LmdjOpfs"],
  lmdj_opfs_list_names:
      (path, length, output, outputLength) => Asyncify.handleAsync(async () => {
        try {
          const names = await LmdjOpfs.listEntries(
              LmdjOpfs.parts(path, length), "file");
          LmdjOpfs.writeNames(names, output, outputLength);
          return 0;
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_list_directories__deps: ["$LmdjOpfs"],
  lmdj_opfs_list_directories:
      (path, length, output, outputLength) => Asyncify.handleAsync(async () => {
        try {
          const names = await LmdjOpfs.listEntries(
              LmdjOpfs.parts(path, length), "directory");
          LmdjOpfs.writeNames(names, output, outputLength);
          return 0;
        } catch (error) {
          return LmdjOpfs.status(error);
        }
      }),

  lmdj_opfs_remove_tree__deps: ["$LmdjOpfs"],
  lmdj_opfs_remove_tree: (path, length) => Asyncify.handleAsync(async () => {
    try {
      const [parent, name] = await LmdjOpfs.parent(
          LmdjOpfs.parts(path, length), false);
      await parent.removeEntry(name, {recursive: true}).catch((error) => {
        if (!(error instanceof DOMException) || error.name !== "NotFoundError") {
          throw error;
        }
      });
      return 0;
    } catch (error) {
      return error instanceof DOMException && error.name === "NotFoundError"
        ? 0
        : LmdjOpfs.status(error);
    }
  }),

  lmdj_opfs_publish_directory_if_absent__deps: ["$LmdjOpfs"],
  lmdj_opfs_publish_directory_if_absent:
      (source, sourceLength, destination, destinationLength) =>
          Asyncify.handleAsync(async () => {
            try {
              const sourceParts = LmdjOpfs.parts(source, sourceLength);
              const destinationParts =
                  LmdjOpfs.parts(destination, destinationLength);
              const [sourceParent, sourceName] =
                  await LmdjOpfs.parent(sourceParts, false);
              const sourceHandle =
                  await sourceParent.getDirectoryHandle(sourceName);
              const [destinationParent, destinationName] =
                  await LmdjOpfs.parent(destinationParts, true);
              if (await LmdjOpfs.exists(destinationParts)) return -4;
              if (typeof sourceHandle.move !== "function") return -8;
              await sourceHandle.move(destinationParent, destinationName);
              return 0;
            } catch (error) {
              return LmdjOpfs.status(error);
            }
          }),

  lmdj_opfs_validate_tree__deps: ["$LmdjOpfs"],
  lmdj_opfs_validate_tree: (path, length) => Asyncify.handleAsync(async () => {
    try {
      const parts = LmdjOpfs.parts(path, length);
      if (parts.length === 0) return 0;
      await LmdjOpfs.directoryExists(parts);
      return 0;
    } catch (error) {
      return LmdjOpfs.status(error);
    }
  }),
});
