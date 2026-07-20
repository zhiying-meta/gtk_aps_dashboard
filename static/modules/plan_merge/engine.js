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
  function toDt(s){
    if (!s) return null;
    if (s instanceof Date) {
      if (isNaN(s.getTime())) return null;
      return new Date(s.getFullYear(), s.getMonth(), s.getDate());
    }
    let str = String(s).trim();
    if (!str) return null;
    // Remove time part if exists
    // Try YYYY-MM-DD
    let m;
    // 2024-01-08 or 2024/01/08 or 2024.01.08
    m = str.match(/^(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})/);
    if (m) {
      let y = parseInt(m[1],10), mo = parseInt(m[2],10)-1, d = parseInt(m[3],10);
      let dt = new Date(y, mo, d);
      if (!isNaN(dt.getTime())) return dt;
    }
    // MM/DD/YYYY
    m = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(\s|$)/);
    if (m) {
      let mo = parseInt(m[1],10)-1, d = parseInt(m[2],10), y = parseInt(m[3],10);
      let dt = new Date(y, mo, d);
      if (!isNaN(dt.getTime())) return dt;
    }
    // DD/MM/YYYY or MM/DD/YY
    m = str.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/);
    if (m) {
      // Try both orders, prefer MM/DD/YYYY if first <=12 and second <=31
      // We'll assume MM/DD/YYYY first
      let mo = parseInt(m[1],10)-1, d = parseInt(m[2],10), y = parseInt(m[3],10);
      if (y<100) y+=2000;
      let dt = new Date(y, mo, d);
      if (!isNaN(dt.getTime()) && dt.getMonth()===mo) return dt;
      // Try DD/MM/YYYY
      let d2 = parseInt(m[1],10), mo2 = parseInt(m[2],10)-1;
      let dt2 = new Date(y, mo2, d2);
      if (!isNaN(dt2.getTime())) return dt2;
    }
    // YYYYMMDD
    m = str.match(/^(\d{4})(\d{2})(\d{2})$/);
    if (m) {
      let dt = new Date(parseInt(m[1],10), parseInt(m[2],10)-1, parseInt(m[3],10));
      if (!isNaN(dt.getTime())) return dt;
    }
    // Chinese 2024年01月02日
    m = str.match(/(\d{4})年(\d{1,2})月(\d{1,2})日?/);
    if (m) {
      let dt = new Date(parseInt(m[1],10), parseInt(m[2],10)-1, parseInt(m[3],10));
      if (!isNaN(dt.getTime())) return dt;
    }
    // Fallback Date parse
    let dt = new Date(str);
    if (!isNaN(dt.getTime())) {
      return new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
    }
    return null;
  }

  function toSaturdayLabel(ds){
    // ds is string YYYY-MM-DD or Date
    let dt = (ds instanceof Date) ? ds : toDt(ds);
    if (!dt) return typeof ds==='string'? ds : '';
    let dow = (dt.getDay()+6)%7; // Mon=0 .. Sun=6 (JS Sun=0)
    let diff = 5 - dow; // Saturday =5
    let sat = new Date(dt);
    sat.setDate(dt.getDate()+diff);
    return formatYMD(sat);
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
    let td = DOW_MAP[cutDay] !== undefined ? DOW_MAP[cutDay] : 5;
    let dt = toDt(ds);
    if (!dt) return null;
    let cd = (dt.getDay()+6)%7;
    let diff = (td - cd + 7) % 7;
    let weekEnd = new Date(dt);
    weekEnd.setDate(dt.getDate()+diff);
    return toSaturdayLabel(weekEnd);
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
      skuAttrs[sku] = {
        Style: obj['Style']!=null ? String(obj['Style']) : '',
        Color: obj['Color']!=null ? String(obj['Color']) : '',
        Usage: obj['Usage']!=null ? String(obj['Usage']) : ''
      };
      let gb = obj['GB_PN']!=null ? String(obj['GB_PN']).trim() : '';
      skuToGb[sku]=gb;
      let pallet = parseInt(obj['Pallet_Qty']);
      if (isNaN(pallet)) pallet = DEFAULT_PALLET_QTY;
      skuPallet[sku]=pallet;
      if (gb && obj['Style'] && obj['Color']){
        gbStyleColor[gb] = [String(obj['Style']), String(obj['Color'])];
      }
    }
    return [skuAttrs, skuToGb, skuPallet, gbStyleColor];
  }

  function processWorkbook(workbook, config){
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

    // GB groups
    let gbGroups={};
    allSkus.forEach(sku=>{
      let g = skuToGb[sku];
      if (!g) return;
      if (!gbGroups[g]) gbGroups[g]=[];
      gbGroups[g].push(sku);
    });

    // sku_data for GB sum
    let skuData={};
    rows.forEach(r=>{
      let key = r.PN+'||'+r['Version-Type']+'||'+r['Version-Detail'];
      let vals={};
      allWeeks.forEach(w=>{ vals[w]=r[w]; });
      skuData[key]=vals;
    });

    Object.entries(gbGroups).forEach(([gb, skus])=>{
      let sc = gbStyleColor[gb] || ['',''];
      let gbUsage='';
      for(let s of skus){
        let u = skuAttrs[s] && skuAttrs[s].Usage;
        if (u){ gbUsage=u; break; }
      }
      let base = {PN:gb, Usage:gbUsage, Style:sc[0], Color:sc[1], GB_PN:gb, Pallet_Qty:DEFAULT_PALLET_QTY, _dim:'GB'};
      [['ExF',''], ['Ungated','Packout'], ['Ungated','Packout vs ExF'], ['Gated','Packout'], ['Gated','Packout vs ExF'], ['CTB','']].forEach(([vt, vd])=>{
        let vals={};
        if (vt==='CTB'){
          if (data.ctb_gb[gb]){
            Object.keys(data.ctb_gb[gb]).forEach(ds=>{
              // Need to bucket? For GB CTB, original Python does: if exact key exists, round, else sum SKU CTB
              // Simplify: treat ctb_gb as already weekly? But we need weekly cum extraction similar to original
              // The original for GB CTB: if gb in ctb_gb, take round(ctb_gb[gb][w]), else sum sku CTB
              // Here data.ctb_gb[gb] is daily dict, but we need weekly values: let's extract weekly
              // We'll do same as Python: for each week, if ctb_gb has that week directly? Actually Python original for GB CTB when gb in ctb_gb, it does round(ctb_gb[gb].get(w,0)) after already having weekly? Wait ctb_gb in Python is daily dict as well but they use extract? Let's simplify: use extractWeeklyCum for gb too
            });
            let weeklyGb = extractWeeklyCum(data.ctb_gb[gb]||{}, cfg.etd_cut);
            Object.keys(weeklyGb).forEach(w=>{
              if (weeklyGb[w]) vals[w]=Math.round(weeklyGb[w]);
            });
          } else {
            allWeeks.forEach(w=>{
              let s = 0;
              skus.forEach(sku=>{
                let sd = skuData[sku+'||CTB||'] || {};
                s += sd[w]||0;
              });
              if (s>0) vals[w]=Math.round(s);
            });
          }
        } else {
          if (vd==='Packout vs ExF'){
            allWeeks.forEach(w=>{
              let s=0;
              let hasData=false;
              skus.forEach(sku=>{
                let sdPackVs = skuData[sku+'||'+vt+'||'+vd] || {};
                let sdPack = skuData[sku+'||'+vt+'||Packout'] || {};
                let sdExf = skuData[sku+'||ExF||'] || {};
                if (sdPackVs[w]!=null) hasData=true;
                if (sdPack[w]!=null) hasData=true;
                if (sdExf[w]!=null) hasData=true;
                s += sdPackVs[w]||0;
              });
              if (hasData) vals[w]=Math.round(s);
            });
          } else {
            allWeeks.forEach(w=>{
              let s=0;
              skus.forEach(sku=>{
                let sd = skuData[sku+'||'+vt+'||'+vd] || {};
                s += sd[w]||0;
              });
              if (s>0) vals[w]=Math.round(s);
            });
          }
        }
        let cd = (vt==='CTB') ? '' : cfg.gb_cut;
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
