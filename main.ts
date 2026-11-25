const { copyFileSync, mkdirSync, readFileSync } = require("node:fs");
const { join, resolve } = require("node:path");

const engine = "node22";

// The sandbox only needs Node's standard library and the committed PNG.
const source = join(__dirname, "entry.png");
const outputDirectory = resolve(process.env.MAKEFUN_OUTPUT_DIR || "/output");
const destination = join(outputDirectory, "entry.png");
const image = readFileSync(source);
const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

if (!image.subarray(0, 8).equals(signature) || image.length > 1_048_576) {
  throw new Error("entry.png must be a complete PNG no larger than 1 MiB.");
}
if (image.readUInt32BE(16) !== 1024 || image.readUInt32BE(20) !== 1024) {
  throw new Error("The rendered entry must be exactly 1024 by 1024 pixels.");
}

mkdirSync(outputDirectory, { recursive: true });
if (source !== destination) {
  copyFileSync(source, destination);
}
console.log(`${engine}: wrote ${destination} (${image.length} bytes)`);
