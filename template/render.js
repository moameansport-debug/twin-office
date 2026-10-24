// Usage: node render.js <product.json> <reel|story> <out.mp4> [fps] [--still t]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

(async () => {
  const [jsonPath, mode = 'reel', out = `${mode}.mp4`, fpsArg] = process.argv.slice(2);
  const stillIdx = process.argv.indexOf('--still');
  const fps = Number(fpsArg) || 30;
  const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
  if (data.image && !/^(file|https?):/.test(data.image))
    data.image = 'file://' + path.resolve(path.dirname(jsonPath), data.image);

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  await page.goto('file://' + path.join(__dirname, 'reel.html'));
  const dur = await page.evaluate(([d, m]) => window.setup(d, m), [data, mode]);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(500);

  if (stillIdx > 0) {
    for (const t of process.argv.slice(stillIdx + 1).map(Number)) {
      await page.evaluate(t => window.render(t), t);
      await page.screenshot({ path: out.replace(/\.\w+$/, `_${t}.png`) });
    }
    await browser.close(); return;
  }

  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-i', '-',
    '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo', '-shortest',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-profile:v', 'high',
    '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const frames = Math.round(dur * fps);
  for (let i = 0; i < frames; i++) {
    await page.evaluate(t => window.render(t), i / fps);
    const buf = await page.screenshot({ type: 'jpeg', quality: 95 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 60 === 0) process.stdout.write(`${mode} ${i}/${frames}\n`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();
  console.log('done', out);
})();
