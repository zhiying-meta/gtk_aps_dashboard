/**
 * Plan Merge Engine - Browser port of app/modules/plan_merge/engine.py + utils.py
 * No backend required. Uses XLSX.js for parsing.
 *
 * Provides: window.PlanMergeEngine.processWorkbook(workbook, config) -> {rows, weeks, week_labels, config, warnings}
 */

(function(global){
  const DOW_MAP = {Monday:0,Tuesday:1,Wednesday:2,Thursday:3,Friday:4,Saturday:5,Sunday:6};
  const DEFAULT_PALLET_QTY = 864;

  // ---------- date helpers ----------
  function pad(n){ return n<10 ? '0'+n : ''+n; }
  function formatYMD(d){
    return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
  }
  // ---- caching for date parsing ----
  const _toDtCache = new Map();
  const _satLabelCache = new Map();
  const _weekLabelCache = new Map();
  function toDt(s){
    if (!s) return null;
    if (s instanceof Date) {
      if (isNaN(s.getTime())) return null;
      return new Date(s.getFullYear(), s.getMonth(), s.getDate());
    }
    let key = String(s);
    if (_toDtCache.has(key)) {
      let cached = _toDtCache.get(key);
      return cached ? new Date(cached.getTime()) : null;
    }
    let str = key.trim();
    if (!str){ _toDtCache.set(key, null); return null; }
    let m, dt=null;
    m = str.match(/^(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})/);
    if (m) {
      let y = parseInt(m[1],10), mo = parseInt(m[2],10)-1, d = parseInt(m[3],10);
      dt = new Date(y, mo, d);
      if (!isNaN(dt.getTime())){ _toDtCache.set(key, new Date(dt.getTime())); return new Date(dt.getTime()); }
    }
    m = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(\s|$)/);
    if (m) {
      let mo = parseInt(m[1],10)-1, d = parseInt(m[2],10), y = parseInt(m[3],10);
      let dtt = new Date(y, mo, d);
      if (!isNaN(dtt.getTime())){ _toDtCache.set(key, new Date(dtt.getTime())); return new Date(dtt.getTime()); }
    }
    m = str.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/);
    if (m) {
      let mo = parseInt(m[1],10)-1, d = parseInt(m[2],10), y = parseInt(m[3],10);
      if (y<100) y+=2000;
      let dtt = new Date(y, mo, d);
      if (!isNaN(dtt.getTime()) && dtt.getMonth()===mo){ _toDtCache.set(key, new Date(dtt.getTime())); return new Date(dtt.getTime()); }
      let d2 = parseInt(m[1],10), mo2 = parseInt(m[2],10)-1;
      let dt2 = new Date(y, mo2, d2);
      if (!isNaN(dt2.getTime())){ _toDtCache.set(key, new Date(dt2.getTime())); return new Date(dt2.getTime()); }
    }
    m = str.match(/^(\d{4})(\d{2})(\d{2})$/);
    if (m) {
      let dtt = new Date(parseInt(m[1],10), parseInt(m[2],10)-1, parseInt(m[3],10));
      if (!isNaN(dtt.getTime())){ _toDtCache.set(key, new Date(dtt.getTime())); return new Date(dtt.getTime()); }
    }
    m = str.match(/(\d{4})年(\d{1,2})月(\d{1,2})日?/);
    if (m) {
      let dtt = new Date(parseInt(m[1],10), parseInt(m[2],10)-1, parseInt(m[3],10));
      if (!isNaN(dtt.getTime())){ _toDtCache.set(key, new Date(dtt.getTime())); return new Date(dtt.getTime()); }
    }
    let dtt = new Date(str);
    if (!isNaN(dtt.getTime())) {
      let nd = new Date(dtt.getFullYear(), dtt.getMonth(), dtt.getDate());
      _toDtCache.set(key, new Date(nd.getTime()));
      return new Date(nd.getTime());
    }
    _toDtCache.set(key, null);
    return null;
  }

  function toSaturdayLabel(ds){
    let cacheKey = ds instanceof Date ? ds.toISOString() : String(ds);
    if (_satLabelCache.has(cacheKey)) return _satLabelCache.get(cacheKey);
    let dt = (ds instanceof Date) ? ds : toDt(ds);
    let res = '';
    if (!dt) res = typeof ds==='string'? ds : '';
    else {
      let dow = (dt.getDay()+6)%7;
      let diff = 5 - dow;
      let sat = new Date(dt);
      sat.setDate(dt.getDate()+diff);
      res = formatYMD(sat);
    }
    _satLabelCache.set(cacheKey, res);
    return res;
  }

  function normalizeDateStr(v){
    if (!v) return '';
    if (v instanceof Date) return formatYMD(v);
    let dt = toDt(v);
    if (dt) return formatYMD(dt);
    return String(v).trim();
  }

  // ---------- aggregation ----------
  function dateToWeekLabel(ds, cutDay){
    let cacheKey = String(ds)+'|'+cutDay;
    if (_weekLabelCache.has(cacheKey)) return _weekLabelCache.get(cacheKey);
    let td = DOW_MAP[cutDay] !== undefined ? DOW_MAP[cutDay] : 5;
    let dt = toDt(ds);
    if (!dt){ _weekLabelCache.set(cacheKey, null); return null; }
    let cd = (dt.getDay()+6)%7;
    let diff = (td - cd + 7) % 7;
    let weekEnd = new Date(dt);
    weekEnd.setDate(dt.getDate()+diff);
    let res = toSaturdayLabel(weekEnd);
    _weekLabelCache.set(cacheKey, res);
    return res;
  }

  function aggregateCumulative(daily, cutDay){
    let td = DOW_MAP[cutDay] !== undefined ? DOW_MAP[cutDay] : 5;
    let dates = Object.keys(daily).sort();
    if (dates.length===0) return {};
    // Build weeks map
    let weeksMap = {}; // wl -> [ds]
    dates.forEach(ds=>{
      let wl = dateToWeekLabel(ds, cutDay);
      if (!wl) return;
      if (!weeksMap[wl]) weeksMap[wl]=[];
      weeksMap[wl].push(ds);
    });
    let firstWl = null, lastWl = null;
    try {
      let sortedWls = Object.keys(weeksMap).sort();
      if (sortedWls.length>0){ firstWl = sortedWls[0]; lastWl = sortedWls[sortedWls.length-1]; }
      // Also need to consider first raw date's week label and last
      if (dates.length>0){
        let fw = dateToWeekLabel(dates[0], cutDay);
        let lw = dateToWeekLabel(dates[dates.length-1], cutDay);
        if (!firstWl || fw < firstWl) firstWl = fw;
        if (!lastWl || lw > lastWl) lastWl = lw;
      }
    } catch(e){}
    if (!firstWl || !lastWl) return {};

    let allWeeks = [];
    let cur = toDt(firstWl);
    let end = toDt(lastWl);
    while(cur && end && cur <= end){
      allWeeks.push(formatYMD(cur));
      cur.setDate(cur.getDate()+7);
    }
    let result = {};
    let running = 0;
    allWeeks.forEach(wl=>{
      let dss = weeksMap[wl] || [];
      dss.sort();
      dss.forEach(ds=>{
        running += (daily[ds] || 0);
      });
      if (running>0) result[wl] = Math.round(running);
    });
    return result;
  }

  function aggregateEtdFromPackout(daily, etdCut, offsetDays){
    if (!daily || Object.keys(daily).length===0) return {};
    let off = parseInt(offsetDays);
    if (isNaN(off) || off<=0) return aggregateCumulative(daily, etdCut);
    let shifted = {};
    Object.entries(daily).forEach(([ds, qty])=>{
      let dt = toDt(ds);
      if (!dt) return;
      let newDt = new Date(dt);
      newDt.setDate(dt.getDate()+off);
      let newDs = formatYMD(newDt);
      shifted[newDs] = (shifted[newDs]||0) + (parseFloat(qty)||0);
    });
    return aggregateCumulative(shifted, etdCut);
  }

  function extractWeeklyCum(daily, cutDay){
    let weeksMap = {};
    Object.keys(daily).forEach(ds=>{
      let dt = toDt(ds);
      if (!dt) return;
      let td = DOW_MAP[cutDay] !== undefined ? DOW_MAP[cutDay] : 5;
      let cd = (dt.getDay()+6)%7;
      let diff = (td - cd + 7)%7;
      let weekEnd = new Date(dt);
      weekEnd.setDate(dt.getDate()+diff);
      let satLabel = toSaturdayLabel(weekEnd);
      if (!weeksMap[satLabel]) weeksMap[satLabel]=[];
      weeksMap[satLabel].push(ds);
    });
    let result = {};
    Object.keys(weeksMap).sort().forEach(wl=>{
      let dl = weeksMap[wl].sort();
      if (dl.length>0){
        let last = dl[dl.length-1];
        if (daily[last]) result[wl] = Math.round(daily[last]);
      }
    });
    return result;
  }

  // ---------- sheet reading ----------
  function sheetToRows(sheet){
    // sheet is XLSX sheet object. Use XLSX.utils.sheet_to_json with header:1
    if (!sheet) return [];
    let aoa = XLSX.utils.sheet_to_json(sheet, {header:1, defval:null});
    return aoa;
  }

  function readSheetFromAOA(aoa, keyCol){
    if (!aoa || aoa.length===0) return {};
    let headers = aoa[0].map(h=> h==null? '' : String(h).trim());
    if (!keyCol){
      if (headers.includes('PN')) keyCol='PN';
      else if (headers.includes('SKU')) keyCol='SKU';
      else keyCol=headers[0];
    }
    let ki = headers.indexOf(keyCol);
    if (ki<0) ki=0;
    let result = {};
    for(let r=1;r<aoa.length;r++){
      let row = aoa[r];
      if (!row) continue;
      let pn = row[ki];
      if (pn==null || String(pn).trim()==='') continue;
      pn = String(pn).trim();
      let vals = {};
      for(let ci=0; ci<headers.length; ci++){
        if (ci===ki) continue;
        let h = headers[ci];
        if (!h) continue;
        let hStr = normalizeDateStr(h);
        if (!hStr) continue;
        let v = row[ci];
        if (v==null || v==='') continue;
        let num = parseFloat(v);
        if (!isNaN(num)){
          vals[hStr]=num;
        }
      }
      if (Object.keys(vals).length>0){
        result[pn]=vals;
      }
    }
    return result;
  }

  function readSkuMasterFromAOA(aoa){
    if (!aoa || aoa.length===0) return [{}, {}, {}, {}];
    let headers = aoa[0].map(h=> h==null? '' : String(h).trim());
    let skuAttrs={}, skuToGb={}, skuPallet={}, gbStyleColor={};
    for(let r=1;r<aoa.length;r++){
      let row = aoa[r];
      if (!row) continue;
      let obj = {};
      headers.forEach((h,ci)=>{ obj[h]=row[ci]; });
      let sku = obj['SKU']!=null ? String(obj['SKU']).trim() : '';
      if (!sku) continue;
      // Trim to avoid "Dark Havana " vs "Dark Havana" duplicate in Color filter
      skuAttrs[sku] = {
        Style: obj['Style']!=null ? String(obj['Style']).trim() : '',
        Color: obj['Color']!=null ? String(obj['Color']).trim() : '',
        Usage: obj['Usage']!=null ? String(obj['Usage']).trim() : ''
      };
      let gb = obj['GB_PN']!=null ? String(obj['GB_PN']).trim() : '';
      skuToGb[sku]=gb;
      let pallet = parseInt(obj['Pallet_Qty']);
      if (isNaN(pallet)) pallet = DEFAULT_PALLET_QTY;
      skuPallet[sku]=pallet;
      if (gb && obj['Style'] && obj['Color']){
        gbStyleColor[gb] = [String(obj['Style']).trim(), String(obj['Color']).trim()];
      }
    }
    return [skuAttrs, skuToGb, skuPallet, gbStyleColor];
  }

  function processWorkbook(workbook, config){
    // No cross-file cache: every upload is treated as fresh, clear all LRU/date caches
    _toDtCache.clear();
    _satLabelCache.clear();
    _weekLabelCache.clear();

    // config: {exf_cut, etd_cut, output_cut, gb_cut, etd_packout_offset}
    let cfg = {
      exf_cut: (config && config.exf_cut) || 'Saturday',
      etd_cut: (config && config.etd_cut) || 'Saturday',
      output_cut: (config && config.output_cut) || 'Wednesday',
      gb_cut: (config && config.gb_cut) || 'Tuesday',
      etd_packout_offset: (config && config.etd_packout_offset!=null) ? parseInt(config.etd_packout_offset) : 2,
    };
    if (isNaN(cfg.etd_packout_offset) || cfg.etd_packout_offset<0) cfg.etd_packout_offset=2;

    // Find sheets
    let sheetNames = workbook.SheetNames || [];
    let wb = workbook;
    let data = { sku:null, gated:{}, ungated:{}, fcst:{}, ctb:{}, ctb_gb:{} };
    let missing = [];
    // sku_master
    let skuSheetName = sheetNames.find(n=> n==='sku_master' || n.toLowerCase()==='sku_master');
    if (!skuSheetName){
      throw new Error('Missing required sheet: sku_master');
    }
    let skuAoa = sheetToRows(wb.Sheets[skuSheetName]);
    let [skuAttrs, skuToGb, skuPallet, gbStyleColor] = readSkuMasterFromAOA(skuAoa);

    // Helper to find sheet by possible names
    function findSheet(possibles){
      for(let p of possibles){
        let found = sheetNames.find(n=> n===p);
        if (found) return found;
      }
      for(let p of possibles){
        let found = sheetNames.find(n=> n.toLowerCase()===p.toLowerCase());
        if (found) return found;
      }
      return null;
    }

    let gatedName = findSheet(['plan_output_gated']);
    if (gatedName){
      let aoa = sheetToRows(wb.Sheets[gatedName]);
      data.gated = readSheetFromAOA(aoa);
    } else missing.push('plan_output_gated');

    let ungatedName = findSheet(['plan_output_ungated']);
    if (ungatedName){
      let aoa = sheetToRows(wb.Sheets[ungatedName]);
      data.ungated = readSheetFromAOA(aoa);
    } else missing.push('plan_output_ungated');

    let fcstName = findSheet(['forecast']);
    if (fcstName){
      let aoa = sheetToRows(wb.Sheets[fcstName]);
      data.fcst = readSheetFromAOA(aoa);
    } else missing.push('forecast');

    let ctbName = findSheet(['ctb_sku_cum','ctb_cum']);
    if (ctbName){
      let aoa = sheetToRows(wb.Sheets[ctbName]);
      data.ctb = readSheetFromAOA(aoa, 'SKU');
    } else missing.push('ctb_sku_cum');

    let ctbGbName = findSheet(['ctb_gb_cum','ctb_gb']);
    if (ctbGbName){
      let aoa = sheetToRows(wb.Sheets[ctbGbName]);
      data.ctb_gb = readSheetFromAOA(aoa);
    } else missing.push('ctb_gb_cum');

    let allPns = new Set(Object.keys(skuAttrs));
    [data.gated, data.ungated, data.fcst, data.ctb].forEach(d=>{
      Object.keys(d).forEach(k=>{ if (skuAttrs[k]) allPns.add(k); });
    });
    let allSkus = Array.from(allPns).filter(s=> skuAttrs[s]).sort();

    // Aggregations
    let agg = {};
    [['GATED_PACK', data.gated, cfg.output_cut], ['UNGATED_PACK', data.ungated, cfg.output_cut], ['FCST', data.fcst, cfg.exf_cut]].forEach(([label, d, cut])=>{
      agg[label]={};
      allSkus.forEach(sku=>{
        let daily = d[sku] || {};
        agg[label][sku] = aggregateCumulative(daily, cut);
      });
    });
    let offsetN = cfg.etd_packout_offset;
    [['GATED_ETD', data.gated, cfg.etd_cut], ['UNGATED_ETD', data.ungated, cfg.etd_cut]].forEach(([label, d, cut])=>{
      agg[label]={};
      allSkus.forEach(sku=>{
        let daily = d[sku] || {};
        agg[label][sku]=aggregateEtdFromPackout(daily, cut, offsetN);
      });
    });

    let allWeeksSet = new Set();
    Object.values(agg).forEach(a=>{
      Object.values(a).forEach(v=>{
        Object.keys(v).forEach(w=> allWeeksSet.add(w));
      });
    });
    allSkus.forEach(sku=>{
      if (data.ctb[sku]){
        let w = extractWeeklyCum(data.ctb[sku], cfg.etd_cut);
        Object.keys(w).forEach(ww=> allWeeksSet.add(ww));
      }
    });

    // Expand to earliest raw date
    let allRawDates = new Set();
    [data.gated, data.ungated, data.fcst, data.ctb].forEach(d=>{
      Object.values(d).forEach(v=> Object.keys(v).forEach(ds=> allRawDates.add(ds)));
    });
    Object.values(data.ctb_gb).forEach(v=> Object.keys(v).forEach(ds=> allRawDates.add(ds)));

    if (allRawDates.size>0){
      let sortedRaw = Array.from(allRawDates).sort();
      let earliestSat = toSaturdayLabel(sortedRaw[0]);
      if (allWeeksSet.size>0){
        let minWeek = Array.from(allWeeksSet).sort()[0];
        if (earliestSat < minWeek){
          let cur = toDt(earliestSat);
          let end = toDt(minWeek);
          while(cur && end && cur < end){
            allWeeksSet.add(formatYMD(cur));
            cur.setDate(cur.getDate()+7);
          }
        }
      } else {
        // if no weeks yet, at least add earliest
        allWeeksSet.add(earliestSat);
      }
    }

    let allWeeks = Array.from(allWeeksSet).sort();

    function fill(vals){
      let o={};
      allWeeks.forEach(w=>{ o[w]= (vals && vals[w]!=null) ? vals[w] : null; });
      return o;
    }
    function diff(b,s){
      if (!b) return {};
      let ks = new Set([...Object.keys(b), ...Object.keys(s||{})]);
      let r={};
      ks.forEach(k=>{ r[k]=(b[k]||0)-(s[k]||0); });
      return r;
    }

    let rows=[];
    // Build rows
    allSkus.forEach(sku=>{
      let a = skuAttrs[sku] || {};
      let style = a.Style||'', color=a.Color||'', usage=a.Usage||'';
      let gb = skuToGb[sku]||'';
      let pallet = skuPallet[sku]||DEFAULT_PALLET_QTY;

      let ue = agg['UNGATED_ETD'][sku] || {};
      let up = agg['UNGATED_PACK'][sku] || {};
      let ge = agg['GATED_ETD'][sku] || {};
      let gp = agg['GATED_PACK'][sku] || {};
      let exf = agg['FCST'][sku] || {};

      // pallet rounding for ETD
      let ueRounded={}, geRounded={};
      Object.entries(ue).forEach(([w,v])=>{ if(v && v>0) ueRounded[w]= Math.floor(v/pallet)*pallet; });
      Object.entries(ge).forEach(([w,v])=>{ if(v && v>0) geRounded[w]= Math.floor(v/pallet)*pallet; });

      let ctb={};
      if (data.ctb[sku]){
        ctb = extractWeeklyCum(data.ctb[sku], cfg.etd_cut);
      }

      let base = {PN:sku, Usage:usage, Style:style, Color:color, GB_PN:gb, Pallet_Qty:pallet, _dim:'FG'};
      rows.push(Object.assign({}, base, {'Version-Type':'ExF','Version-Detail':'','Cut Day':cfg.exf_cut}, fill(exf)));
      rows.push(Object.assign({}, base, {'Version-Type':'Ungated','Version-Detail':'ETD','Cut Day':cfg.etd_cut}, fill(ueRounded)));
      rows.push(Object.assign({}, base, {'Version-Type':'Ungated','Version-Detail':'ETD vs ExF','Cut Day':cfg.etd_cut}, fill(diff(ueRounded, exf))));
      rows.push(Object.assign({}, base, {'Version-Type':'Ungated','Version-Detail':'Packout','Cut Day':cfg.output_cut}, fill(up)));
      rows.push(Object.assign({}, base, {'Version-Type':'Ungated','Version-Detail':'Packout vs ExF','Cut Day':cfg.output_cut}, fill(diff(up, exf))));
      rows.push(Object.assign({}, base, {'Version-Type':'Gated','Version-Detail':'ETD','Cut Day':cfg.etd_cut}, fill(geRounded)));
      rows.push(Object.assign({}, base, {'Version-Type':'Gated','Version-Detail':'ETD vs ExF','Cut Day':cfg.etd_cut}, fill(diff(geRounded, exf))));
      rows.push(Object.assign({}, base, {'Version-Type':'Gated','Version-Detail':'Packout','Cut Day':cfg.output_cut}, fill(gp)));
      rows.push(Object.assign({}, base, {'Version-Type':'Gated','Version-Detail':'Packout vs ExF','Cut Day':cfg.output_cut}, fill(diff(gp, exf))));
      rows.push(Object.assign({}, base, {'Version-Type':'CTB','Version-Detail':'','Cut Day':''}, fill(ctb)));
    });

    // ---- GB handling fix + canonicalization (SKU master is source of truth, case-insensitive) ----
    // Build lower -> canonical map from SKU master GBs
    let skuGbLowerToCanonical = {};
    Object.values(skuToGb).forEach(g=>{
      if (!g) return;
      let low = g.toLowerCase();
      if (!(low in skuGbLowerToCanonical)) skuGbLowerToCanonical[low]=g;
    });
    Object.keys(gbStyleColor).forEach(g=>{
      let low = g.toLowerCase();
      if (!(low in skuGbLowerToCanonical)) skuGbLowerToCanonical[low]=g;
    });

    function toCanonicalGb(gbPn){
      if (!gbPn) return gbPn;
      let low = gbPn.toLowerCase();
      if (skuGbLowerToCanonical[low]) return skuGbLowerToCanonical[low];
      // Alias: try Style+Color match for DEEP BLACK vs Black (low cost)
      let rest = gbPn.toUpperCase().startsWith('GB-') ? gbPn.slice(3) : gbPn;
      let idx = rest.lastIndexOf('-');
      if (idx!==-1){
        let parsedStyle = rest.slice(0, idx).trim();
        let parsedColor = rest.slice(idx+1).trim();
        const styleMapLocal = {'rec m':'Rectangle M','rec l':'Rectangle L','rec':'Rectangle M','panthos m':'Panthos M','panthos s':'Panthos S','pantos s':'Pantos S','bold':'Bold','slim':'Slim','cateye':'Cateye'};
        let fullParsedStyle = styleMapLocal[parsedStyle.toLowerCase()] || parsedStyle;
        for(let canonGb in gbStyleColor){
          let sc = gbStyleColor[canonGb];
          if (!sc) continue;
          let c = sc[1]||'', s = sc[0]||'';
          let cmatch = false;
          if (c.toLowerCase()===parsedColor.toLowerCase()) cmatch=true;
          else if (parsedColor.toLowerCase().includes('low cost') && c.toLowerCase().includes('low cost')) cmatch=true;
          if (!cmatch) continue;
          if (fullParsedStyle.toLowerCase().includes(s.toLowerCase()) || s.toLowerCase().includes(fullParsedStyle.toLowerCase())){
            return canonGb;
          }
        }
      }
      return gbPn;
    }

    function canonicalizeMixedDict(d){
      let newDict={};
      if (!d) return newDict;
      Object.entries(d).forEach(([pn, daily])=>{
        if (skuAttrs[pn]){
          newDict[pn]=daily;
        } else if (pn.startsWith('GB-')) {
          let canon = toCanonicalGb(pn);
          if (newDict[canon]){
            Object.entries(daily).forEach(([ds, qty])=>{
              newDict[canon][ds] = (newDict[canon][ds]||0) + qty;
            });
          } else {
            newDict[canon] = Object.assign({}, daily);
          }
        }
        // else: FR/LT/RT etc. ignored — only FG (SKU) and GB are needed
      });
      return newDict;
    }
    function canonicalizeGbDict(d){
      let newDict={};
      if (!d) return newDict;
      Object.entries(d).forEach(([pn, daily])=>{
        if (!pn.startsWith('GB-')) return; // only GB-
        let canon = toCanonicalGb(pn);
        if (newDict[canon]){
          Object.entries(daily).forEach(([ds, qty])=>{
            newDict[canon][ds] = (newDict[canon][ds]||0) + qty;
          });
        } else {
          newDict[canon] = Object.assign({}, daily);
        }
      });
      return newDict;
    }

    // Apply canonicalization
    data.gated = canonicalizeMixedDict(data.gated);
    data.ungated = canonicalizeMixedDict(data.ungated);
    data.ctb_gb = canonicalizeGbDict(data.ctb_gb);

    let allGbSet = new Set();
    Object.values(skuToGb).forEach(g=>{
      if (g) allGbSet.add(g);
    });
    [data.gated, data.ungated, data.ctb_gb].forEach(d=>{
      if (!d) return;
      Object.keys(d).forEach(pn=>{
        if (!skuAttrs[pn] && pn.startsWith('GB-')) allGbSet.add(pn);
      });
    });

    let gbGroups={};
    allSkus.forEach(sku=>{
      let g = skuToGb[sku];
      if (!g) return;
      let gCanon = toCanonicalGb(g);
      if (!gbGroups[gCanon]) gbGroups[gCanon]=[];
      gbGroups[gCanon].push(sku);
    });
    allGbSet.forEach(gb=>{
      if (!gbGroups[gb]) gbGroups[gb]=[];
    });

    // sku_data for GB sum
    let skuData={};
    rows.forEach(r=>{
      let key = r.PN+'||'+r['Version-Type']+'||'+r['Version-Detail'];
      let vals={};
      allWeeks.forEach(w=>{ vals[w]=r[w]; });
      skuData[key]=vals;
    });

    function getGbPack(daily){
      if (!daily || Object.keys(daily).length===0) return {};
      return aggregateCumulative(daily, cfg.gb_cut);
    }
    function getGbEtd(daily){
      if (!daily || Object.keys(daily).length===0) return {};
      let raw = aggregateEtdFromPackout(daily, cfg.gb_cut, cfg.etd_packout_offset);
      let rounded={};
      Object.entries(raw).forEach(([wk,v])=>{
        if (v && v>0) rounded[wk]= Math.floor(v/DEFAULT_PALLET_QTY)*DEFAULT_PALLET_QTY;
      });
      return rounded;
    }
    function directVs(baseVals, exfV){
      let res={};
      allWeeks.forEach(w=>{
        let b = baseVals[w];
        let e = exfV[w];
        if (b==null && e==null) return;
        res[w]=Math.round((b||0)-(e||0));
      });
      return res;
    }

    // Helper to infer GB style/color when mapping missing (e.g. Black (low cost) vs DEEP BLACK)
    function inferGbStyleColor(gbPn){
      if (gbStyleColor[gbPn]) return gbStyleColor[gbPn];
      let low = gbPn.toLowerCase();
      for(let k in gbStyleColor){
        if (k.toLowerCase()===low) return gbStyleColor[k];
      }
      // Parse GB-Style-Color
      let rest = gbPn.toUpperCase().startsWith('GB-') ? gbPn.slice(3) : gbPn;
      let idx = rest.lastIndexOf('-');
      let parsedStyle = idx!==-1 ? rest.slice(0, idx).trim() : rest.trim();
      let parsedColor = idx!==-1 ? rest.slice(idx+1).trim() : '';
      // Try find SKU whose Color matches parsedColor (case-insensitive)
      if (parsedColor){
        const lowStyleMap = {'rec m':'Rectangle M','rec l':'Rectangle L','rec':'Rectangle M'};
        const fullStyleLocal = lowStyleMap[parsedStyle.toLowerCase()] || parsedStyle;
        // 1. exact color + style match first
        for(let sku in skuAttrs){
          let c = skuAttrs[sku] && skuAttrs[sku].Color ? skuAttrs[sku].Color : '';
          let s = skuAttrs[sku] && skuAttrs[sku].Style ? skuAttrs[sku].Style : '';
          if (c.toLowerCase()===parsedColor.toLowerCase()){
            if (fullStyleLocal.toLowerCase().includes(s.toLowerCase()) || s.toLowerCase().includes(fullStyleLocal.toLowerCase()) ||
                parsedStyle.toLowerCase().includes(s.toLowerCase()) || s.toLowerCase().includes(parsedStyle.toLowerCase())){
              return [s, c];
            }
          }
        }
        // 1b. any exact color
        for(let sku in skuAttrs){
          let c = skuAttrs[sku] && skuAttrs[sku].Color ? skuAttrs[sku].Color : '';
          if (c.toLowerCase()===parsedColor.toLowerCase()){
            return [skuAttrs[sku].Style || fullStyleLocal, c];
          }
        }
        // 2. low cost special
        if (parsedColor.toLowerCase().includes('low cost')){
          for(let sku in skuAttrs){
            let c = skuAttrs[sku] && skuAttrs[sku].Color ? skuAttrs[sku].Color : '';
            let s = skuAttrs[sku] && skuAttrs[sku].Style ? skuAttrs[sku].Style : '';
            if (c.toLowerCase().includes('low cost')){
              if (fullStyleLocal.toLowerCase().includes(s.toLowerCase()) || s.toLowerCase().includes(fullStyleLocal.toLowerCase())){
                return [s, c];
              }
            }
          }
          for(let sku in skuAttrs){
            let c = skuAttrs[sku] && skuAttrs[sku].Color ? skuAttrs[sku].Color : '';
            if (c.toLowerCase().includes('low cost')){
              return [fullStyleLocal, c];
            }
          }
        }
        // 3. contains but require style match to avoid BLACK matching Black Ice
        for(let sku in skuAttrs){
          let c = skuAttrs[sku] && skuAttrs[sku].Color ? skuAttrs[sku].Color : '';
          let s = skuAttrs[sku] && skuAttrs[sku].Style ? skuAttrs[sku].Style : '';
          let styleMatch = parsedStyle.toLowerCase().includes(s.toLowerCase().split(' ')[0]) || s.toLowerCase().includes(parsedStyle.toLowerCase().split(' ')[0]);
          if (!styleMatch) continue;
          if (parsedColor.toLowerCase().includes(c.toLowerCase()) || c.toLowerCase().includes(parsedColor.toLowerCase())){
            return [s || parsedStyle, c];
          }
        }
      }
      // Map abbreviations
      const styleMap = {'rec m':'Rectangle M','rec l':'Rectangle L','rec':'Rectangle M','panthos m':'Panthos M','panthos s':'Panthos S','pantos s':'Pantos S','bold':'Bold','slim':'Slim','cateye':'Cateye'};
      let fullStyle = parsedStyle;
      let lowStyle = parsedStyle.toLowerCase();
      if (styleMap[lowStyle]) fullStyle = styleMap[lowStyle];
      else {
        for(let sku in skuAttrs){
          let s = skuAttrs[sku] && skuAttrs[sku].Style ? skuAttrs[sku].Style : '';
          if (lowStyle.includes(s.toLowerCase().split(' ')[0]) || s.toLowerCase().includes(lowStyle.split(' ')[0])){
            fullStyle = s;
            break;
          }
        }
      }
      return [fullStyle, parsedColor];
    }
    function inferGbUsage(gbPn, skusList){
      for(let s of skusList){
        let u = skuAttrs[s] && skuAttrs[s].Usage;
        if (u) return u;
      }
      let rest = gbPn.toUpperCase().startsWith('GB-') ? gbPn.slice(3) : gbPn;
      let idx = rest.lastIndexOf('-');
      let parsedColor = idx!==-1 ? rest.slice(idx+1).trim() : '';
      if (parsedColor){
        for(let sku in skuAttrs){
          let c = skuAttrs[sku] && skuAttrs[sku].Color ? skuAttrs[sku].Color : '';
          if (c.toLowerCase()===parsedColor.toLowerCase()){
            let u = skuAttrs[sku] && skuAttrs[sku].Usage;
            if (u) return u;
          }
        }
        for(let sku in skuAttrs){
          let c = skuAttrs[sku] && skuAttrs[sku].Color ? skuAttrs[sku].Color : '';
          if (parsedColor.toLowerCase().includes('low cost') && c.toLowerCase().includes('low cost')){
            let u = skuAttrs[sku] && skuAttrs[sku].Usage;
            if (u) return u;
          }
        }
        for(let sku in skuAttrs){
          let c = skuAttrs[sku] && skuAttrs[sku].Color ? skuAttrs[sku].Color : '';
          if (parsedColor.toLowerCase().includes(c.toLowerCase()) || c.toLowerCase().includes(parsedColor.toLowerCase())){
            let u = skuAttrs[sku] && skuAttrs[sku].Usage;
            if (u) return u;
          }
        }
      }
      return 'MP';
    }

    Object.entries(gbGroups).forEach(([gb, skus])=>{
      let sc = inferGbStyleColor(gb);
      // If still blank and skus exist, try first sku
      if ((!sc[0] || !sc[1]) && skus.length>0){
        for(let s of skus){
          let attrs = skuAttrs[s];
          if (attrs){
            sc = [sc[0] || attrs.Style || '', sc[1] || attrs.Color || ''];
            if (sc[0] && sc[1]) break;
          }
        }
      }
      let gbUsage = '';
      for(let s of skus){
        let u = skuAttrs[s] && skuAttrs[s].Usage;
        if (u){ gbUsage=u; break; }
      }
      if (!gbUsage) gbUsage = inferGbUsage(gb, skus);
      let base = {PN:gb, Usage:gbUsage, Style:sc[0], Color:sc[1], GB_PN:gb, Pallet_Qty:DEFAULT_PALLET_QTY, _dim:'GB'};

      // ExF sum SKU
      let exfVals={};
      allWeeks.forEach(w=>{
        let s=0;
        let has=false;
        skus.forEach(sku=>{
          let v = skuData[sku+'||ExF||'] ? skuData[sku+'||ExF||'][w] : null;
          if (v!=null){ has=true; s+=v||0; }
        });
        if (s>0) exfVals[w]=Math.round(s);
      });

      let gatedDaily = (data.gated && data.gated[gb]) ? data.gated[gb] : {};
      let ungatedDaily = (data.ungated && data.ungated[gb]) ? data.ungated[gb] : {};
      let hasGatedDirect = gatedDaily && Object.keys(gatedDaily).length>0;
      let hasUngatedDirect = ungatedDaily && Object.keys(ungatedDaily).length>0;

      let gpVals = hasGatedDirect ? getGbPack(gatedDaily) : {};
      let upVals = hasUngatedDirect ? getGbPack(ungatedDaily) : {};
      let geVals = hasGatedDirect ? getGbEtd(gatedDaily) : {};
      let ueVals = hasUngatedDirect ? getGbEtd(ungatedDaily) : {};

      if (!hasGatedDirect){
        allWeeks.forEach(w=>{
          let s=0;
          skus.forEach(sku=>{
            let sd = skuData[sku+'||Gated||Packout'] || {};
            s+= sd[w]||0;
          });
          if (s>0) gpVals[w]=Math.round(s);
        });
      }
      if (!hasUngatedDirect){
        allWeeks.forEach(w=>{
          let s=0;
          skus.forEach(sku=>{
            let sd = skuData[sku+'||Ungated||Packout'] || {};
            s+= sd[w]||0;
          });
          if (s>0) upVals[w]=Math.round(s);
        });
      }
      if (!hasGatedDirect){
        allWeeks.forEach(w=>{
          let s=0;
          skus.forEach(sku=>{
            let sd = skuData[sku+'||Gated||ETD'] || {};
            s+= sd[w]||0;
          });
          if (s>0) geVals[w]=Math.round(s);
        });
      }
      if (!hasUngatedDirect){
        allWeeks.forEach(w=>{
          let s=0;
          skus.forEach(sku=>{
            let sd = skuData[sku+'||Ungated||ETD'] || {};
            s+= sd[w]||0;
          });
          if (s>0) ueVals[w]=Math.round(s);
        });
      }

      let gpVs={}, upVs={}, geVs={}, ueVs={};
      if (hasGatedDirect || hasUngatedDirect){
        gpVs = directVs(gpVals, exfVals);
        upVs = directVs(upVals, exfVals);
        geVs = directVs(geVals, exfVals);
        ueVs = directVs(ueVals, exfVals);
      }
      if (!hasGatedDirect){
        // fallback vs logic with has_data
        gpVs={};
        allWeeks.forEach(w=>{
          let s=0; let hasData=false;
          skus.forEach(sku=>{
            let sdVs = skuData[sku+'||Gated||Packout vs ExF']||{};
            let sdPack = skuData[sku+'||Gated||Packout']||{};
            let sdExf = skuData[sku+'||ExF||']||{};
            if (sdVs[w]!=null) hasData=true;
            if (sdPack[w]!=null) hasData=true;
            if (sdExf[w]!=null) hasData=true;
            s+= sdVs[w]||0;
          });
          if (hasData) gpVs[w]=Math.round(s);
        });
        geVs={};
        allWeeks.forEach(w=>{
          let s=0; let hasData=false;
          skus.forEach(sku=>{
            let sdVs = skuData[sku+'||Gated||ETD vs ExF']||{};
            let sdEtd = skuData[sku+'||Gated||ETD']||{};
            let sdExf = skuData[sku+'||ExF||']||{};
            if (sdVs[w]!=null || sdEtd[w]!=null || sdExf[w]!=null) hasData=true;
            s+= sdVs[w]||0;
          });
          if (hasData) geVs[w]=Math.round(s);
        });
      }
      if (!hasUngatedDirect){
        upVs={};
        allWeeks.forEach(w=>{
          let s=0; let hasData=false;
          skus.forEach(sku=>{
            let sdVs = skuData[sku+'||Ungated||Packout vs ExF']||{};
            let sdPack = skuData[sku+'||Ungated||Packout']||{};
            let sdExf = skuData[sku+'||ExF||']||{};
            if (sdVs[w]!=null) hasData=true;
            if (sdPack[w]!=null) hasData=true;
            if (sdExf[w]!=null) hasData=true;
            s+= sdVs[w]||0;
          });
          if (hasData) upVs[w]=Math.round(s);
        });
        ueVs={};
        allWeeks.forEach(w=>{
          let s=0; let hasData=false;
          skus.forEach(sku=>{
            let sdVs = skuData[sku+'||Ungated||ETD vs ExF']||{};
            let sdEtd = skuData[sku+'||Ungated||ETD']||{};
            let sdExf = skuData[sku+'||ExF||']||{};
            if (sdVs[w]!=null || sdEtd[w]!=null || sdExf[w]!=null) hasData=true;
            s+= sdVs[w]||0;
          });
          if (hasData) ueVs[w]=Math.round(s);
        });
      }

      // CTB
      let ctbVals={};
      if (data.ctb_gb && data.ctb_gb[gb]){
        let weeklyGb = extractWeeklyCum(data.ctb_gb[gb]||{}, cfg.etd_cut);
        Object.keys(weeklyGb).forEach(w=>{
          if (weeklyGb[w]) ctbVals[w]=Math.round(weeklyGb[w]);
        });
      } else {
        allWeeks.forEach(w=>{
          let s=0;
          skus.forEach(sku=>{
            let sd = skuData[sku+'||CTB||'] || {};
            s+= sd[w]||0;
          });
          if (s>0) ctbVals[w]=Math.round(s);
        });
      }

      // Include full 10 types like FG for completeness
      let versionDefs = [
        ['ExF','',exfVals, cfg.exf_cut],
        ['Ungated','ETD', ueVals, cfg.gb_cut],
        ['Ungated','ETD vs ExF', ueVs, cfg.gb_cut],
        ['Ungated','Packout', upVals, cfg.gb_cut],
        ['Ungated','Packout vs ExF', upVs, cfg.gb_cut],
        ['Gated','ETD', geVals, cfg.gb_cut],
        ['Gated','ETD vs ExF', geVs, cfg.gb_cut],
        ['Gated','Packout', gpVals, cfg.gb_cut],
        ['Gated','Packout vs ExF', gpVs, cfg.gb_cut],
        ['CTB','', ctbVals, '']
      ];
      versionDefs.forEach(([vt, vd, vals, cd])=>{
        rows.push(Object.assign({}, base, {'Version-Type':vt,'Version-Detail':vd,'Cut Day':cd}, fill(vals)));
      });
    });

    let wl={};
    allWeeks.forEach(w=>{
      try{
        let dt = toDt(w);
        if (!dt) { wl[w]=w; return;}
        let wk = Math.floor((dt.getDate()-1)/7)+1;
        let months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        let b = months[dt.getMonth()];
        wl[w]= b+' Wk'+wk+' ('+b+' '+pad(dt.getDate())+')';
      }catch(e){ wl[w]=w; }
    });

    let warnings=[];
    if (missing.length>0) warnings.push('Missing optional sheets (left empty): '+missing.join(', '));
    else warnings.push('All 6 sheets present ✓');

    return {rows, weeks:allWeeks, week_labels:wl, config:cfg, warnings};
  }

  // Export
  global.PlanMergeEngine = {
    processWorkbook,
    aggregateCumulative,
    aggregateEtdFromPackout,
    extractWeeklyCum,
    toDt,
    formatYMD,
    normalizeDateStr
  };

})(window);
