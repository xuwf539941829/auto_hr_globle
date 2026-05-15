/**
 * Patches fs.readlink / fs.promises.readlink to convert EISDIR → ENOENT.
 *
 * On some Windows filesystems (virtual/network drives) that do not implement
 * NTFS reparse-point queries, Node.js returns EISDIR when readlink is called
 * on a regular file.  Webpack's enhanced-resolve treats ENOENT as "not a
 * symlink" but propagates EISDIR as a fatal error.  This shim makes the two
 * behaviours equivalent, so Next.js builds work on those filesystems.
 *
 * All three APIs are patched because Next.js uses callback, sync, AND
 * promises variants across its main process and build worker processes.
 */
const fs = require("fs");

function eisdir2enoent(path) {
  return Object.assign(
    new Error("ENOENT: no such file or directory, readlink '" + path + "'"),
    { errno: -4058, code: "ENOENT", syscall: "readlink", path }
  );
}

// ── callback API ─────────────────────────────────────────────────────────────
const _rl = fs.readlink.bind(fs);
fs.readlink = function patchedReadlink(path, options, callback) {
  const cb   = typeof options === "function" ? options : callback;
  const opts = typeof options === "function" ? undefined : options;
  _rl(path, opts, (err, linkString) => {
    cb(err && err.code === "EISDIR" ? eisdir2enoent(path) : err, linkString);
  });
};

// ── sync API ──────────────────────────────────────────────────────────────────
const _rls = fs.readlinkSync.bind(fs);
fs.readlinkSync = function patchedReadlinkSync(path, options) {
  try {
    return _rls(path, options);
  } catch (err) {
    if (err && err.code === "EISDIR") throw eisdir2enoent(path);
    throw err;
  }
};

// ── promises API ──────────────────────────────────────────────────────────────
const _rlp = fs.promises.readlink.bind(fs.promises);
fs.promises.readlink = async function patchedReadlinkPromise(path, options) {
  try {
    return await _rlp(path, options);
  } catch (err) {
    if (err && err.code === "EISDIR") throw eisdir2enoent(path);
    throw err;
  }
};
