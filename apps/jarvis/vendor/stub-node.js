// Browser stub for node:fs / node:path. The Anthropic SDK reaches these only from
// filesystem-upload helpers, which this app never calls. Throwing (rather than
// returning undefined) keeps an accidental use loud instead of silently wrong.
const boom = (name) => () => { throw new Error(`node builtin "${name}" is unavailable in the browser bundle`); };
export const createReadStream = boom('fs.createReadStream');
export const promises = new Proxy({}, { get: (_, k) => boom(`fs.promises.${String(k)}`) });
export const readFileSync = boom('fs.readFileSync');
export const statSync = boom('fs.statSync');
export const basename = (p = '') => String(p).split('/').pop();
export const resolve = (...a) => a.join('/');
export const join = (...a) => a.join('/');
export const dirname = (p = '') => String(p).split('/').slice(0, -1).join('/') || '.';
export const extname = (p = '') => { const b = basename(p); const i = b.lastIndexOf('.'); return i > 0 ? b.slice(i) : ''; };
export default { createReadStream, promises, readFileSync, statSync, basename, resolve, join, dirname, extname };
