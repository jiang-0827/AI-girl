#!/usr/bin/env node
// Deterministically remove detached ground/shadow components from the
// preprocessed alpha PNGs. The largest connected foreground component is the
// character body; any smaller component sitting near the bottom of the canvas
// with a low-saturation, light color is a residual ground/shadow blob and is
// cleared. Idempotent: re-running changes nothing.
// Usage: node tools-alpha/clean-residue.mjs <incomingDir>
import { readdir, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';

const [, , inputDirArg] = process.argv;
const inputDir = path.resolve(inputDirArg ?? 'incoming-assets');
const BOTTOM_RATIO = 0.84;   // component bottom must be in the lower part of the canvas
const MAX_SATURATION = 46;   // max RGB max-min for a grey-ish blob
const MIN_LUMINANCE = 150;   // min average luminance
const MAX_SIZE_RATIO = 0.30; // blob must be smaller than 30% of total foreground

async function cleanFile(absolute) {
  const image = sharp(absolute);
  const { data, info } = await image.raw().toBuffer({ resolveWithObject: true });
  const { width, height } = info;
  const channels = info.channels;
  const alphaAt = (x, y) => data[(y * width + x) * channels + 3];
  const rgbAt = (x, y) => {
    const i = (y * width + x) * channels;
    return [data[i], data[i + 1], data[i + 2]];
  };
  const labels = new Int32Array(width * height).fill(-1);
  const components = [];
  let nextLabel = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const idx = y * width + x;
      if (alphaAt(x, y) <= 16 || labels[idx] !== -1) continue;
      const stack = [idx];
      labels[idx] = nextLabel;
      const comp = { pixels: [], minX: width, maxX: 0, minY: height, maxY: 0 };
      while (stack.length) {
        const cur = stack.pop();
        const cx = cur % width;
        const cy = Math.floor(cur / width);
        comp.pixels.push(cur);
        if (cx < comp.minX) comp.minX = cx;
        if (cx > comp.maxX) comp.maxX = cx;
        if (cy < comp.minY) comp.minY = cy;
        if (cy > comp.maxY) comp.maxY = cy;
        for (const [nx, ny] of [[cx - 1, cy], [cx + 1, cy], [cx, cy - 1], [cx, cy + 1]]) {
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          const nidx = ny * width + nx;
          if (labels[nidx] === -1 && alphaAt(nx, ny) > 16) {
            labels[nidx] = nextLabel;
            stack.push(nidx);
          }
        }
      }
      components.push({ label: nextLabel, ...comp });
      nextLabel += 1;
    }
  }
  if (!components.length) return { changed: false };
  const totalPixels = components.reduce((sum, comp) => sum + comp.pixels.length, 0);
  const mainLabel = components.reduce((best, comp) => (comp.pixels.length > best.pixels.length ? comp : best)).label;
  const removed = [];
  for (const comp of components) {
    if (comp.label === mainLabel) continue;
    const bottom = comp.maxY / height;
    const sizeRatio = comp.pixels.length / totalPixels;
    if (bottom < BOTTOM_RATIO || sizeRatio > MAX_SIZE_RATIO) continue;
    let sumR = 0, sumG = 0, sumB = 0;
    for (const idx of comp.pixels) {
      const x = idx % width;
      const y = Math.floor(idx / width);
      const [r, g, b] = rgbAt(x, y);
      sumR += r; sumG += g; sumB += b;
    }
    const avgR = sumR / comp.pixels.length;
    const avgG = sumG / comp.pixels.length;
    const avgB = sumB / comp.pixels.length;
    const saturation = Math.max(avgR, avgG, avgB) - Math.min(avgR, avgG, avgB);
    const luminance = 0.299 * avgR + 0.587 * avgG + 0.114 * avgB;
    if (saturation <= MAX_SATURATION && luminance >= MIN_LUMINANCE) {
      for (const idx of comp.pixels) data[idx * channels + 3] = 0;
      removed.push({ pixels: comp.pixels.length, bottom: Number(bottom.toFixed(3)), saturation: Number(saturation.toFixed(1)), luminance: Number(luminance.toFixed(1)), bbox: [comp.minX, comp.minY, comp.maxX, comp.maxY] });
    }
  }
  if (!removed.length) return { changed: false };
  const tmp = `${absolute}.tmp-clean.png`;
  await sharp(data, { raw: { width, height, channels } }).png({ compressionLevel: 9 }).toFile(tmp);
  await rename(tmp, absolute);
  return { changed: true, removed };
}

async function main() {
  const files = (await readdir(inputDir, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && /\.png$/i.test(entry.name))
    .map((entry) => entry.name);
  const report = [];
  for (const name of files) {
    const absolute = path.join(inputDir, name);
    const result = await cleanFile(absolute);
    if (result.changed) report.push({ name, removed: result.removed });
  }
  await writeFile(path.join(inputDir, 'residue-clean-report.json'), JSON.stringify(report, null, 2) + '\n', 'utf8');
  console.log(`Cleaned residue in ${report.length} file(s). Report: ${path.join(inputDir, 'residue-clean-report.json')}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
