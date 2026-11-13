const fs = require('fs');
const path = require('path');

const BASE_URL = "https://mcggdb.com";
const HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
};

async function fetchHtml(url) {
  const res = await fetch(url, { headers: HEADERS });
  return await res.text();
}

function unescapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&#39;/g, "'");
}

function stripHtml(str) {
  if (!str) return "";
  return str.replace(/<[^>]*>/g, '').trim();
}

// ---------------------------------------------------------------------------
// 1. SCRAPER COMMANDERS (JSON FORMAT - 100% DATA NETRAL)
// ---------------------------------------------------------------------------
async function scrapeCommanders() {
  console.log("\n==========================================");
  console.log("1. MEMULAI SCRAPING COMMANDER (42 Commander ke JSON)...");
  console.log("==========================================");

  const catalogUrl = `${BASE_URL}/id/commanders/`;
  const catalogHtml = await fetchHtml(catalogUrl);
  const linkMatches = [...catalogHtml.matchAll(/href="(\/id\/commanders\/[a-z0-9-]+\/)"/gi)];
  const commanderUrls = [...new Set(linkMatches.map(m => BASE_URL + m[1]))];

  console.log(`Ditemukan ${commanderUrls.length} commander.`);
  const allCommanders = [];

  for (let i = 0; i < commanderUrls.length; i++) {
    const url = commanderUrls[i];
    const slug = url.replace(/\/+$/, '').split('/').pop();
    process.stdout.write(`[${i + 1}/${commanderUrls.length}] Commander: ${slug}... `);

    try {
      const htmlStr = await fetchHtml(url);

      let name = slug.toUpperCase();
      const h1Match = htmlStr.match(/<h1>([^<]+)/i);
      if (h1Match) name = stripHtml(h1Match[1]).replace(/\s*Commander.*$/i, '').trim();

      const badges = [...htmlStr.matchAll(/<span class="badge">([^<]+)<\/span>/gi)]
        .map(m => stripHtml(m[1]));
      let rawTipe = badges.find(b => 
        !/^Tier\s+/i.test(b) && 
        !/^(Mudah|Sedang|Sulit)$/i.test(b) && 
        !/daftar Commander/i.test(b)
      ) || "Umum";

      // Mapping tipe commander resmi
      let tipeCommander = "Strategi";
      const lowerT = rawTipe.toLowerCase();
      if (lowerT.includes("carry") || lowerT.includes("tempo dan duel")) {
        tipeCommander = "Pertarungan";
      } else if (lowerT.includes("bertahan hidup") || lowerT.includes("survival")) {
        tipeCommander = "Daya tahan";
      } else if (lowerT.includes("ekonomi") || lowerT.includes("item") || lowerT.includes("suplai")) {
        tipeCommander = "Suplai";
      } else if (lowerT.includes("roll") || lowerT.includes("shop") || lowerT.includes("strategi") || lowerT.includes("card")) {
        tipeCommander = "Strategi";
      }
        !/^Tier\s+/i.test(b) && 
        !/^(Mudah|Sedang|Sulit)$/i.test(b) && 
        !/daftar Commander/i.test(b)
      ) || "Umum";

      // Level 1 Skill
      let skill1Text = "";
      const l1Match = htmlStr.match(/Level 1\s*<button.*?<\/h2>\s*<p[^>]*>(.*?)<\/p>/is);
      if (l1Match) skill1Text = stripHtml(l1Match[1]);

      // Level 2 Skill
      let skill2Text = "";
      const l2Match = htmlStr.match(/Level 2\s*<span.*?<\/h2>\s*<p[^>]*>(.*?)<\/p>/is);
      if (l2Match) skill2Text = stripHtml(l2Match[1]);

      const tipeSkill1 = /ketuk tombol skill|gunakan skill/i.test(skill1Text) ? "Aktif" : "Pasif";
      const tipeSkill2 = /ketuk tombol skill|gunakan skill/i.test(skill2Text) ? "Aktif" : "Pasif";

      allCommanders.push({
        nama_commander: name,
        slug: slug,
        tipe_commander: tipeCommander,
        tipe_skill_1: tipeSkill1,
        skill_1: skill1Text,
        tipe_skill_2: tipeSkill2,
        skill_2: skill2Text,
        url: url
      });

      console.log("[OK]");
    } catch (err) {
      console.log(`[ERROR: ${err.message}]`);
    }

    await new Promise(r => setTimeout(r, 120));
  }

  const outPath = path.join(__dirname, "commanders.json");
  fs.writeFileSync(outPath, JSON.stringify(allCommanders, null, 2), "utf-8");
  console.log(`[SUKSES] Commanders disimpan ke: ${outPath}`);
}

// ---------------------------------------------------------------------------
// 2. SCRAPER HEROES (JSON FORMAT + Posisi Barisan, Mana Awal, Max Mana)
// ---------------------------------------------------------------------------
async function scrapeHeroes() {
  console.log("\n==========================================");
  console.log("2. MEMULAI SCRAPING HEROES (58 Hero ke JSON)...");
  console.log("==========================================");

  const catalogUrl = `${BASE_URL}/id/s7/heroes/`;
  const catalogHtml = await fetchHtml(catalogUrl);
  const linkMatches = [...catalogHtml.matchAll(/href="(\/id\/s7\/heroes\/[a-z0-9-]+\/)"/gi)];
  const heroUrls = [...new Set(linkMatches.map(m => BASE_URL + m[1]))];

  console.log(`Ditemukan ${heroUrls.length} hero.`);
  const allHeroes = [];

  for (let i = 0; i < heroUrls.length; i++) {
    const url = heroUrls[i];
    const slug = url.replace(/\/+$/, '').split('/').pop();
    process.stdout.write(`[${i + 1}/${heroUrls.length}] Hero: ${slug}... `);

    try {
      const htmlStr = await fetchHtml(url);

      let name = slug.toUpperCase();
      const h1Match = htmlStr.match(/<h1>(?:Panduan\s+)?([^<]+)/i);
      if (h1Match) name = stripHtml(h1Match[1]).replace(/\s*MCGG.*$/i, '').trim();

      const badges = [...htmlStr.matchAll(/<span class="badge">([^<]+)<\/span>|<a class="badge"[^>]*>([^<]+)<\/a>/gi)]
        .map(m => stripHtml(m[1] || m[2]));

      let gold = badges.find(b => /gold/i.test(b)) || "";
      let posisiBarisan = badges.find(b => /barisan/i.test(b)) || "";

      const synergyBadges = badges.filter(b => !/gold/i.test(b) && !/barisan/i.test(b));
      let faksi = synergyBadges[0] ? synergyBadges[0].replace(/\s*\d.*$/, '').trim() : "";
      let role1 = synergyBadges[1] ? synergyBadges[1].replace(/\s*\d.*$/, '').trim() : "-";
      let role2 = synergyBadges[2] ? synergyBadges[2].replace(/\s*\d.*$/, '').trim() : "-";
      let sinergiLengkap = synergyBadges.map(s => s.replace(/\s*\d.*$/, '').trim()).join(", ");

      let skillDesc = "";
      const kemMatch = htmlStr.match(/Kemampuan\s*terverifikasi.*?<\/h2>\s*<p[^>]*>(.*?)<\/p>/is);
      if (kemMatch) skillDesc = stripHtml(kemMatch[1]);

      const statsObj = { "1★": {}, "2★": {}, "3★": {} };
      const islandMatch = htmlStr.match(/<astro-island[^>]*component-url="[^"]*StarToggle[^"]*"[^>]*props="([^"]*)"/i);
      if (islandMatch) {
        const decoded = unescapeHtml(islandMatch[1]);
        const jsonProps = JSON.parse(decoded);
        const starRows = jsonProps.rows ? jsonProps.rows[1] : [];
        for (const row of starRows) {
          const starNum = row[1].star[1];
          const values = row[1].values[1];
          const target = statsObj[`${starNum}★`];
          if (target) {
            for (const item of values) {
              const sName = item[1][0][1];
              const sVal = item[1][1][1];
              target[sName] = sVal;
            }
          }
        }
      }

      const maxMana = statsObj["1★"]["Mana"] || statsObj["2★"]["Mana"] || statsObj["3★"]["Mana"] || "0";
      const manaAwal = "0";

      let items = [];
      const itemMatch = htmlStr.match(/<b>Item yang direkomendasikan game:<\/b>(.*?)(?:<\/p>|<p)/is);
      if (itemMatch) {
        const itemLinks = [...itemMatch[1].matchAll(/<a[^>]*>(.*?)<\/a>/gi)];
        items = itemLinks.map(m => stripHtml(m[1])).filter(Boolean);
      }

      const peluangRoll = {};
      const caraBlock = htmlStr.substring(htmlStr.indexOf("Cara mendapatkan"));
      const thMatch = caraBlock.match(/<tr>\s*<th>Level kamu<\/th>(.*?)<\/tr>/is);
      const tdMatch = caraBlock.match(/<tr>\s*<td>Peluang hero ini muncul dalam sekali roll<\/td>(.*?)<\/tr>/is);
      if (thMatch && tdMatch) {
        const ths = [...thMatch[1].matchAll(/<th>(.*?)<\/th>/gi)].map(m => stripHtml(m[1]));
        const tds = [...tdMatch[1].matchAll(/<td>(.*?)<\/td>/gi)].map(m => stripHtml(m[1]));
        for (let idx = 0; idx < ths.length; idx++) {
          peluangRoll[`Level ${ths[idx]}`] = tds[idx] || "-";
        }
      }

      allHeroes.push({
        nama_hero: name,
        slug: slug,
        harga_gold: gold,
        posisi_barisan: posisiBarisan,
        mana_awal: manaAwal,
        max_mana: maxMana,
        faksi: faksi,
        role_1: role1,
        role_2: role2,
        sinergi_lengkap: sinergiLengkap,
        deskripsi_skill: skillDesc,
        statistik_1_bintang: statsObj["1★"],
        statistik_2_bintang: statsObj["2★"],
        statistik_3_bintang: statsObj["3★"],
        rekomendasi_item: items,
        peluang_roll_shop: peluangRoll,
        url: url
      });

      console.log("[OK]");
    } catch (err) {
      console.log(`[ERROR: ${err.message}]`);
    }

    await new Promise(r => setTimeout(r, 120));
  }

  const outPath = path.join(__dirname, "heroes.json");
  fs.writeFileSync(outPath, JSON.stringify(allHeroes, null, 2), "utf-8");
  console.log(`[SUKSES] Heroes disimpan ke: ${outPath}`);
}

async function main() {
  await scrapeCommanders();
  await scrapeHeroes();
  console.log("\n==========================================");
  console.log("SEMUA DATA JSON BERHASIL DISIMPAN!");
  console.log("==========================================");
}

main();