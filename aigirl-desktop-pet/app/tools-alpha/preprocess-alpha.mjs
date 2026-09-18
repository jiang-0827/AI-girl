#!/usr/bin/env node
// Pre-process generated flat-white-background assets into real-alpha PNGs.
// The white background is removed with a border flood-fill (4-connected),
// then a small alpha feather is applied so no white halo remains on dark
// desktops. Internal white details (e.g. white hair-dot ornaments) are kept
// because they are not connected to the image border.
// Usage: node tools-alpha/preprocess-alpha.mjs <incomingDir> <rawBackupDir>
import { mkdir, readdir, copyFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';

const [, , inputDirArg, backupDirArg] = process.argv;
const inputDir = path.resolve(inputDirArg ?? 'incoming-assets');
const backupDir = path.resolve(backupDirArg ?? 'source-raw');
const BORDER_THRESHOLD = 30; // colour distance from pure white treated as background
const FEATHER_PX = 1.5;

function distanceFromWhite(r, g, b) {
  const dr = r - 255, dg = g - 255, db = b - 255;
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

async function processFile(relative, absolute) {
  const image = sharp(absolute);
  const meta = await image.metadata();
  if (!meta.width || !meta.height) throw new Error(`${relative}: no dimensions`);
  // Idempotence: files that already carry a real alpha channel are left untouched.
  if (meta.hasAlpha && meta.format === 'png') {
    const { data, info } = await image.raw().toBuffer({ resolveWithObject: true });
    let nonOpaque = 0;
    for (let i = 0; i < info.width * info.height; i += 1) {
      if (data[i * info.channels + 3] < 250) nonOpaque += 1;
    }
    if (nonOpaque / (info.width * info.height) >= 0.005) {
      return { relative, width: meta.width, height: meta.height, skipped: true, foregroundRatio: nonOpaque / (info.width * info.height) };
    }
  }
  const { data, info } = await image
    .ensureAlpha()
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const { width, height } = info;
  const channels = 4;
  const alpha = new Uint8Array(width * height);
  const visited = new Uint8Array(width * height);
  const queue = [];
  const isBackground = (x, y) => {
    const i = (y * width + x) * channels;
    return distanceFromWhite(data[i], data[i + 1], data[i + 2]) < BORDER_THRESHOLD;
  };
  const push = (x, y) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const idx = y * width + x;
    if (visited[idx]) return;
    visited[idx] = 1;
    queue.push(idx);
  };
  for (let x = 0; x < width; x += 1) { push(x, 0); push(x, height - 1); }
  for (let y = 0; y < height; y += 1) { push(0, y); push(width - 1, y); }
  let head = 0;
  while (head < queue.length) {
    const idx = queue[head];
    head += 1;
    const x = idx % width;
    const y = Math.floor(idx / width);
    if (!isBackground(x, y)) continue;
    alpha[idx] = 0;
    push(x - 1, y); push(x + 1, y); push(x, y - 1); push(x, y + 1);
  }
  // Everything not visited/background keeps alpha 255.
  const foregroundPixels = [];
  for (let idx = 0; idx < width * height; idx += 1) {
    if (visited[idx] && alpha[idx] === 0) continue;
    alpha[idx] = 255;
    foregroundPixels.push(idx);
  }
  if (foregroundPixels.length === 0) throw new Error(`${relative}: foreground is empty`);
  // Feather: for each foreground pixel within FEATHER_PX of a background pixel,
  // scale alpha down proportionally (soft edge, no white halo).
  const feathered = new Uint8Array(alpha);
  const radius = Math.max(1, Math.round(FEATHER_PX * Math.max(width, height) / 2048));
  const step = 1;
  for (let pass = 1; pass <= radius; pass += 1) {
    const next = new Uint8Array(feathered);
    for (const idx of foregroundPixels) {
      if (feathered[idx] === 0) continue;
      const x = idx % width;
      const y = Math.floor(idx / width);
      let touching = false;
      for (let oy = -step; oy <= step && !touching; oy += step) {
        for (let ox = -step; ox <= step && !touching; ox += step) {
          if (ox === 0 && oy === 0) continue;
          const nx = x + ox, ny = y + oy;
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          const nidx = ny * width + nx;
          if (feathered[nidx] === 0) { touching = true; break; }
        }
      }
      if (touching) next[idx] = Math.max(0, feathered[idx] - Math.round(255 / radius));
    }
    feathered.set(next);
  }
  const out = Buffer.alloc(width * height * channels);
  for (let idx = 0; idx < width * height; idx += 1) {
    out[idx * channels] = data[idx * channels];
    out[idx * channels + 1] = data[idx * channels + 1];
    out[idx * channels + 2] = data[idx * channels + 2];
    out[idx * channels + 3] = feathered[idx];
  }
  const tmpPath = `${absolute}.tmp-${process.pid}.png`;
  await sharp(out, { raw: { width, height, channels } }).png({ compressionLevel: 9 }).toFile(tmpPath);
  await rename(tmpPath, absolute);
  const nonOpaque = feathered.filter((v) => v < 250).length;
  return { relative, width, height, foregroundRatio: foregroundPixels.length / (width * height), transparentPixels: nonOpaque };
}

async function main() {
  await mkdir(backupDir, { recursive: true });
  const files = [];
  const walk = async (dir, prefix) => {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const relative = path.posix.join(prefix, entry.name);
      const absolute = path.join(dir, entry.name);
      if (entry.isDirectory()) await walk(absolute, relative);
      else if (/\.(png|jpe?g|webp)$/i.test(entry.name)) files.push({ relative, absolute });
    }
  };
  await walk(inputDir, '');
  const report = [];
  for (const file of files) {
    await copyFile(file.absolute, path.join(backupDir, file.relative.replaceAll('/', '__')));
    const result = await processFile(file.relative, file.absolute);
    report.push(result);
  }
  await writeFile(path.join(inputDir, 'alpha-preprocess-report.json'), JSON.stringify(report, null, 2) + '\n', 'utf8');
  console.log(`Preprocessed ${report.length} files -> real alpha PNG. Report: ${path.join(inputDir, 'alpha-preprocess-report.json')}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
