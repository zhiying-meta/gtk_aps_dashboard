/**
 * IO Report Engine - Browser port of app/modules/io_report/engine.py
 * Provides client-side processing for 3 files: master, schedule, balance
 * No backend needed.
 */
(function(global){
  const REPORTS = ['daily_input','daily_output','daily_checkin','daily_checkout','cum_input','cum_output','cum_checkin','cum_checkout','balance'];

  function toDatetime(v){
    if (!v) return null;
    if (v instanceof Date){
      if (isNaN(v.getTime())) return null;
      return new Date(v.getFullYear(), v.getMonth(), v.getDate());
    }
    let s = String(v).trim();
    if (!s) return null;
    // Try YYYY/MM/DD, YYYY-MM-DD etc.
    let m;
    m = s.match(/^(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})/);
    if (m){
      let dt = new Date(parseInt(m[1],10), parseInt(m[2],10)-1, parseInt(m[3],10));
      if (!isNaN(dt.getTime())) return dt;
    }
    m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (m){
      let dt = new Date(parseInt(m[3],10), parseInt(m[1],10)-1, parseInt(m[2],10));
      if (!isNaN(dt.getTime())) return dt;
    }
    m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2})$/);
    if (m){
      let y = parseInt(m[3],10); if (y<100) y+=2000;
      let dt = new Date(y, parseInt(m[1],10)-1, parseInt(m[2],10));
      if (!isNaN(dt.getTime())) return dt;
    }
    let dt = new Date(s);
    if (!isNaN(dt.getTime())) return new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
    return null;
  }

  function firstDayOfISOWeek(year, week){
    // Use ISO week to Monday
    // Jan 4 is always in week 1
    let jan4 = new Date(year, 0, 4);
    let day = (jan4.getDay()+6)%7; // Mon=0
    let mondayWeek1 = new Date(jan4);
    mondayWeek1.setDate(jan4.getDate()-day);
    let target = new Date(mondayWeek1);
    target.setDate(mondayWeek1.getDate() + (week-1)*7);
    return target;
  }

  function getColIndex(headers, target){
    if (!headers) return -1;
    for(let i=0;i<headers.length;i++){
      if (headers[i]===target) return i;
    }
    for(let i=0;i<headers.length;i++){
      if (headers[i] && String(headers[i]).trim()===target.trim()) return i;
    }
    for(let i=0;i<headers.length;i++){
      if (headers[i] && String(headers[i]).trim().toLowerCase()===target.toLowerCase()) return i;
    }
    return -1;
  }

  function sheetToAOA(sheet){
    if (!sheet) return [];
    return XLSX.utils.sheet_to_json(sheet, {header:1, defval:null});
  }

  function parseMaster(aoa){
    if (!aoa || aoa.length===0) throw new Error('Master sheet empty');
    let headers = (aoa[0]||[]).map(h=> h==null?'':String(h).trim());
    let itemIdx = getColIndex(headers, 'ITEM_NO');
    let catIdx = getColIndex(headers, 'PRODUCT_CATEGORY');
    let styleIdx = getColIndex(headers, 'PRODUCT_STYLE');
    if (itemIdx<0 || catIdx<0) throw new Error('Master missing ITEM_NO or PRODUCT_CATEGORY, headers='+headers.join(','));
    let itemToCat={}, itemToStyle={}, fgItems=[], gbItems=[];
    let styleFgSet=new Set(), styleGbSet=new Set();
    for(let r=1;r<aoa.length;r++){
      let row=aoa[r]; if(!row) continue;
      let item=row[itemIdx], cat=row[catIdx];
      if (!item || !cat) continue;
      item=String(item).trim(); cat=String(cat).trim();
      if (!item || !cat) continue;
      let style = styleIdx>=0 && row[styleIdx]!=null ? String(row[styleIdx]).trim() : '';
      itemToCat[item]=cat;
      itemToStyle[item]=style;
      if (cat==='成品'){
        fgItems.push(item);
        if (style) styleFgSet.add(style);
      }else if (cat==='GB'){
        gbItems.push(item);
        if (style) styleGbSet.add(style);
      }
    }
    return {
      itemToCat, itemToStyle,
      fgItems: Array.from(new Set(fgItems)).sort(),
      gbItems: Array.from(new Set(gbItems)).sort(),
      styleFg: Array.from(styleFgSet).sort(),
      styleGb: Array.from(styleGbSet).sort()
    };
  }

  function parseSchedule(aoa, itemToCat, itemToStyle){
    if (!aoa || aoa.length===0) return {fg:[], gb:[], lineFg:new Set(), lineGb:new Set()};
    let headers=(aoa[0]||[]).map(h=> h==null?'':String(h).trim());
    let lineIdx=getColIndex(headers,'LINE_CODE');
    let shiftIdx=getColIndex(headers,'SHIFT_NAME');
    let planItemIdx=getColIndex(headers,'PLAN_ITEM');
    let skuIdx=getColIndex(headers,'SKU');
    let dateIdx=getColIndex(headers,'PLAN_DATE');
    let valIdx=getColIndex(headers,'PLAN_VALUE');
    let fg=[], gb=[];
    let lineFg=new Set(), lineGb=new Set();
    let fgSet=new Set(Object.keys(itemToCat).filter(k=> itemToCat[k]==='成品'));
    let gbSet=new Set(Object.keys(itemToCat).filter(k=> itemToCat[k]==='GB'));
    for(let r=1;r<aoa.length;r++){
      let row=aoa[r]; if(!row) continue;
      if (row.length<=Math.max(lineIdx,shiftIdx,planItemIdx,skuIdx,dateIdx,valIdx)) continue;
      let skuRaw=row[skuIdx]; if(!skuRaw) continue;
      let sku=String(skuRaw).trim();
      if (!fgSet.has(sku) && !gbSet.has(sku)) continue;
      let val=0;
      try{ val=parseFloat(row[valIdx])||0; }catch(e){ val=0; }
      let pd=toDatetime(row[dateIdx]);
      if (!pd) continue;
      let sr={
        LineCode: row[lineIdx]!=null? String(row[lineIdx]).trim() : '',
        ShiftName: row[shiftIdx]!=null? String(row[shiftIdx]).trim() : '',
        PlanItem: row[planItemIdx]!=null? String(row[planItemIdx]).trim() : '',
        SKU: sku,
        PlanDate: pd,
        PlanValue: val,
        Style: itemToStyle[sku]||''
      };
      if (fgSet.has(sku)){
        fg.push(sr);
        if (sr.LineCode) lineFg.add(sr.LineCode);
      }else{
        gb.push(sr);
        if (sr.LineCode) lineGb.add(sr.LineCode);
      }
    }
    return {fg, gb, lineFg, lineGb};
  }

  function parseBalance(aoa, itemToCat, itemToStyle){
    if (!aoa || aoa.length===0) return {fg:[], gb:[]};
    let headers=(aoa[0]||[]).map(h=> h==null?'':String(h).trim());
    let dateIdx=getColIndex(headers,'PLAN_DATE');
    let shiftIdx=getColIndex(headers,'SHIFT_NAME');
    let itemIdx=getColIndex(headers,'ITEM_CODE');
    let qtyIdx=getColIndex(headers,'BALANCE_QTY');
    let fg=[], gb=[];
    let fgSet=new Set(Object.keys(itemToCat).filter(k=> itemToCat[k]==='成品'));
    let gbSet=new Set(Object.keys(itemToCat).filter(k=> itemToCat[k]==='GB'));
    for(let r=1;r<aoa.length;r++){
      let row=aoa[r]; if(!row) continue;
      if (row.length<=Math.max(dateIdx,shiftIdx,itemIdx,qtyIdx)) continue;
      let itemRaw=row[itemIdx]; if(!itemRaw) continue;
      let item=String(itemRaw).trim();
      if (!fgSet.has(item) && !gbSet.has(item)) continue;
      let qty=0;
      try{ qty=parseFloat(row[qtyIdx])||0; }catch(e){ qty=0; }
      let pd=toDatetime(row[dateIdx]);
      if (!pd) continue;
      let br={
        PlanDate: pd,
        ShiftName: row[shiftIdx]!=null? String(row[shiftIdx]).trim() : '',
        ItemCode: item,
        BalanceQty: qty,
        Style: itemToStyle[item]||''
      };
      if (fgSet.has(item)) fg.push(br); else gb.push(br);
    }
    return {fg, gb};
  }

  function pad(n){ return n<10?'0'+n:''+n; }
  function fmtMMDD(d){ return pad(d.getMonth()+1)+'/'+pad(d.getDate()); }

  function getColDefs(sched, bal, colDim){
    let seenDate={}, seenShift={};
    let raw=[];
    function addShift(d,s){
      let sk = d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'|'+(s||'');
      if (!seenShift[sk]){
        seenShift[sk]=true;
        raw.push({Date:new Date(d), Label: fmtMMDD(d)+'_'+(s||''), SortDate:new Date(d), SortKey:s||''});
      }
    }
    function addDay(d){
      let dk = d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
      if (!seenDate[dk]){
        seenDate[dk]=true;
        raw.push({Date:new Date(d), Label: fmtMMDD(d), SortDate:new Date(d), SortKey:''});
      }
    }
    function addWeek(d){
      let tmp = new Date(d);
      // ISO week
      let year = tmp.getFullYear();
      // get ISO week
      let jan4 = new Date(year,0,4);
      let day = (jan4.getDay()+6)%7;
      let mondayWeek1 = new Date(jan4); mondayWeek1.setDate(jan4.getDate()-day);
      // compute week of d
      let diff = Math.floor((d - mondayWeek1)/ (7*24*60*60*1000)) +1;
      let wk = year+'-W'+pad(diff);
      if (!seenDate[wk]){
        seenDate[wk]=true;
        let monday = firstDayOfISOWeek(year, diff);
        raw.push({Date:monday, Label: fmtMMDD(monday), SortDate:monday, SortKey:''});
      }
    }
    function addMonth(d){
      let ym = d.getFullYear()+'-'+pad(d.getMonth()+1);
      if (!seenDate[ym]){
        seenDate[ym]=true;
        let first = new Date(d.getFullYear(), d.getMonth(),1);
        let label = pad(d.getMonth()+1)+'月';
        raw.push({Date:first, Label:label, SortDate:first, SortKey:''});
      }
    }
    sched.forEach(r=>{
      if (!r.PlanDate) return;
      if (colDim==='day') addDay(r.PlanDate);
      else if (colDim==='week') addWeek(r.PlanDate);
      else if (colDim==='month') addMonth(r.PlanDate);
      else addShift(r.PlanDate, r.ShiftName);
    });
    bal.forEach(r=>{
      if (!r.PlanDate) return;
      if (colDim==='day') addDay(r.PlanDate);
      else if (colDim==='week') addWeek(r.PlanDate);
      else if (colDim==='month') addMonth(r.PlanDate);
      else addShift(r.PlanDate, r.ShiftName);
    });
    raw.sort((a,b)=>{
      if (a.SortDate - b.SortDate !==0) return a.SortDate - b.SortDate;
      let prio = (k)=>{
        if (k==='白班') return 0;
        if (k==='夜班') return 1;
        return 2;
      };
      return prio(a.SortKey) - prio(b.SortKey) || (a.SortKey||'').localeCompare(b.SortKey||'');
    });
    // dedup by label
    let seen={}, out=[];
    raw.forEach(c=>{
      if (!seen[c.Label]){
        seen[c.Label]=true;
        out.push(c);
      }
    });
    return out;
  }

  function colLabels(cols){ return cols.map(c=>c.Label); }

  function aggKeyForSched(r, colDim){
    if (!r.PlanDate) return '';
    let d=r.PlanDate;
    if (colDim==='day') return fmtMMDD(d);
    if (colDim==='week'){
      let year = d.getFullYear();
      let jan4 = new Date(year,0,4);
      let day = (jan4.getDay()+6)%7;
      let mondayWeek1 = new Date(jan4); mondayWeek1.setDate(jan4.getDate()-day);
      let diff = Math.floor((d - mondayWeek1)/(7*24*60*60*1000))+1;
      let monday = firstDayOfISOWeek(year, diff);
      return fmtMMDD(monday);
    }
    if (colDim==='month') return pad(d.getMonth()+1)+'月';
    return fmtMMDD(d)+'_'+(r.ShiftName||'');
  }

  function balColKey(r, colDim){
    if (!r.PlanDate) return '';
    let d=r.PlanDate;
    if (colDim==='day') return fmtMMDD(d);
    if (colDim==='week'){
      let year = d.getFullYear();
      let jan4 = new Date(year,0,4);
      let day = (jan4.getDay()+6)%7;
      let mondayWeek1 = new Date(jan4); mondayWeek1.setDate(jan4.getDate()-day);
      let diff = Math.floor((d - mondayWeek1)/(7*24*60*60*1000))+1;
      let monday = firstDayOfISOWeek(year, diff);
      return fmtMMDD(monday);
    }
    if (colDim==='month') return pad(d.getMonth()+1)+'月';
    return fmtMMDD(d)+'_'+(r.ShiftName||'');
  }

  function buildSched(sched, dimCol, cols, planItem, cumulative, colDim){
    let filtered = sched.filter(r=> r.PlanItem===planItem);
    if (filtered.length===0) return [[],[]];
    let actualDim = dimCol;
    if (dimCol==='ITEM_NO') actualDim='SKU';
    if (dimCol==='STYLE') actualDim='STYLE';
    // dim mapping
    let agg={}, pivot={}, dimSet=new Set();
    filtered.forEach(r=>{
      let dimVal='';
      if (actualDim==='LINE_CODE') dimVal=r.LineCode||'';
      else if (actualDim==='STYLE') dimVal=r.Style||'';
      else dimVal=r.SKU||'';
      let colL = aggKeyForSched(r, colDim);
      let key = dimVal+'|'+colL;
      agg[key]=(agg[key]||0)+(r.PlanValue||0);
    });
    Object.entries(agg).forEach(([k,v])=>{
      let parts=k.split('|');
      let dimVal=parts[0];
      let colL=parts.slice(1).join('|');
      if (!pivot[dimVal]) pivot[dimVal]={};
      pivot[dimVal][colL]=(pivot[dimVal][colL]||0)+v;
      dimSet.add(dimVal);
    });
    let colHeaders = colLabels(cols);
    let rows=[];
    Array.from(dimSet).sort().forEach(dim=>{
      let entry={};
      entry[dimCol]=dim;
      let vals=pivot[dim]||{};
      if (cumulative){
        let running=0;
        colHeaders.forEach(h=>{
          running+=vals[h]||0;
          entry[h]=Math.round(running);
        });
      }else{
        colHeaders.forEach(h=>{
          entry[h]=Math.round(vals[h]||0);
        });
      }
      rows.push(entry);
    });
    return [colHeaders, rows];
  }

  function buildSchedDetail(sched, cols, planItem, cumulative, colDim){
    let filtered = sched.filter(r=> r.PlanItem===planItem);
    if (filtered.length===0) return [[],[]];
    let agg={}, pivot={}, rowSet={};
    filtered.forEach(r=>{
      let rk = (r.SKU||'')+'|'+(r.LineCode||'')+'|'+(r.Style||'');
      let colL = aggKeyForSched(r, colDim);
      let key = rk+'|'+colL;
      agg[key]=(agg[key]||0)+(r.PlanValue||0);
    });
    Object.entries(agg).forEach(([k,v])=>{
      let parts=k.split('|');
      let colL=parts.pop();
      let rk=parts.join('|');
      if (!pivot[rk]) pivot[rk]={};
      pivot[rk][colL]=(pivot[rk][colL]||0)+v;
      rowSet[rk]=true;
    });
    let colHeaders=colLabels(cols);
    let rows=[];
    Object.keys(rowSet).sort((a,b)=>{
      let ap=a.split('|'), bp=b.split('|');
      // sort by line, item, style
      if (ap[1]<bp[1]) return -1;
      if (ap[1]>bp[1]) return 1;
      if (ap[0]<bp[0]) return -1;
      if (ap[0]>bp[0]) return 1;
      return 0;
    }).forEach(rk=>{
      let parts=rk.split('|');
      let item=parts[0], line=parts[1], style=parts[2];
      let entry={ITEM_NO:item, LINE_CODE:line, STYLE:style};
      let vals=pivot[rk]||{};
      if (cumulative){
        let running=0;
        colHeaders.forEach(h=>{
          running+=vals[h]||0;
          entry[h]=Math.round(running);
        });
      }else{
        colHeaders.forEach(h=>{ entry[h]=Math.round(vals[h]||0); });
      }
      rows.push(entry);
    });
    return [colHeaders, rows];
  }

  function buildBalance(bal, dimCol, cols, colDim){
    if (!bal || bal.length===0) return [[],[]];
    if (dimCol==='LINE_CODE') return [[],[]];
    function dimFn(r){ return dimCol==='STYLE' ? (r.Style||'') : (r.ItemCode||''); }
    let agg={}, dimSet=new Set();
    bal.forEach(r=>{
      let dv=dimFn(r);
      let key=dv+'|'+balColKey(r, colDim);
      agg[key]=(agg[key]||0)+(r.BalanceQty||0);
      dimSet.add(dv);
    });
    let pivot={};
    Object.entries(agg).forEach(([k,v])=>{
      let idx=k.lastIndexOf('|');
      let dv=k.substring(0,idx);
      let col=k.substring(idx+1);
      if (!pivot[dv]) pivot[dv]={};
      pivot[dv][col]=(pivot[dv][col]||0)+v;
    });
    let colHeaders=colLabels(cols);
    let rows=[];
    Array.from(dimSet).sort().forEach(dim=>{
      let entry={}; entry[dimCol]=dim;
      let vals=pivot[dim]||{};
      colHeaders.forEach(h=>{ entry[h]=Math.round(vals[h]||0); });
      rows.push(entry);
    });
    return [colHeaders, rows];
  }

  function balToSched(bal){
    return bal.map(b=> ({
      SKU:b.ItemCode, Style:b.Style||'', PlanDate:b.PlanDate, ShiftName:b.ShiftName||'', PlanValue:b.BalanceQty||0, PlanItem:'INPUT', LineCode:''
    }));
  }

  function buildOneReport(sched, bal, rtype, dim, cols, colDim){
    let rt = rtype.toLowerCase();
    if (rt==='boh' || rt==='balance') rt='balance';
    const mapping={
      daily_input:['INPUT', false],
      daily_output:['OUTPUT', false],
      daily_checkin:['CHECKIN', false],
      daily_checkout:['CHECKOUT', false],
      cum_input:['INPUT', true],
      cum_output:['OUTPUT', true],
      cum_checkin:['CHECKIN', true],
      cum_checkout:['CHECKOUT', true]
    };
    if (rt==='balance'){
      if (dim==='detail') return buildSchedDetail(balToSched(bal), cols, 'INPUT', false, colDim);
      return buildBalance(bal, dim, cols, colDim);
    }
    let plan,cum;
    if (mapping[rt]){
      [plan,cum]=mapping[rt];
    }else{
      if (rt.includes('input')){ plan='INPUT'; cum=rt.includes('cum'); }
      else if (rt.includes('output')){ plan='OUTPUT'; cum=rt.includes('cum'); }
      else if (rt.includes('checkin')){ plan='CHECKIN'; cum=rt.includes('cum'); }
      else if (rt.includes('checkout')){ plan='CHECKOUT'; cum=rt.includes('cum'); }
      else return [[],[]];
    }
    if (dim==='detail') return buildSchedDetail(sched, cols, plan, cum, colDim);
    return buildSched(sched, dim, cols, plan, cum, colDim);
  }

  function getMeta(cache, group, colDim){
    let isFg = (group==='成品' || group==='FG');
    let sched = isFg ? cache.schedFg : cache.schedGb;
    let bal = isFg ? cache.balFg : cache.balGb;
    let cols = getColDefs(sched, bal, colDim);
    return {
      date_shift_pairs: cols.map(c=>c.Label),
      line_codes: isFg ? cache.lineFg : cache.lineGb,
      items: isFg ? cache.fgItems : cache.gbItems,
      styles: isFg ? cache.styleFg : cache.styleGb,
      lines_fg: cache.lineFg,
      lines_gb: cache.lineGb,
      items_fg: cache.fgItems,
      items_gb: cache.gbItems,
      styles_fg: cache.styleFg,
      styles_gb: cache.styleGb
    };
  }

  function buildReportsForGroup(cache, dim, colDim, group, lineCodeFilter, itemNoFilter, styleFilter){
    let isFg = (group==='成品' || group==='FG');
    let sched = (isFg ? cache.schedFg : cache.schedGb).slice();
    let bal = (isFg ? cache.balFg : cache.balGb).slice();
    if (lineCodeFilter){
      sched=sched.filter(s=> s.LineCode===lineCodeFilter);
    }
    if (itemNoFilter){
      sched=sched.filter(s=> s.SKU===itemNoFilter);
      bal=bal.filter(b=> b.ItemCode===itemNoFilter);
    }
    if (styleFilter){
      sched=sched.filter(s=> s.Style===styleFilter);
      bal=bal.filter(b=> b.Style===styleFilter);
    }
    let colDefs = getColDefs(sched, bal, colDim);
    if (!colDefs || colDefs.length===0) return [{}, []];
    let result={};
    for(let rtype of REPORTS){
      let [colH, rows] = buildOneReport(sched, bal, rtype, dim, colDefs, colDim);
      result[rtype]={columns:colH, rows:rows};
    }
    result.pair_count=colDefs.length;
    return [result, colDefs];
  }

  function loadFromWorkbooks(masterWb, schedWb, balWb){
    // masterWb, schedWb, balWb are XLSX WorkBook objects
    let masterSheet = masterWb.Sheets[masterWb.SheetNames[0]];
    let masterAoa = sheetToAOA(masterSheet);
    let masterParsed = parseMaster(masterAoa);

    let schedSheet = schedWb.Sheets[schedWb.SheetNames[0]];
    let schedAoa = sheetToAOA(schedSheet);
    let schedParsed = parseSchedule(schedAoa, masterParsed.itemToCat, masterParsed.itemToStyle);

    let balSheet = balWb.Sheets[balWb.SheetNames[0]];
    let balAoa = sheetToAOA(balSheet);
    let balParsed = parseBalance(balAoa, masterParsed.itemToCat, masterParsed.itemToStyle);

    let cache = {
      itemToCat: masterParsed.itemToCat,
      itemToStyle: masterParsed.itemToStyle,
      fgItems: masterParsed.fgItems,
      gbItems: masterParsed.gbItems,
      schedFg: schedParsed.fg,
      schedGb: schedParsed.gb,
      balFg: balParsed.fg,
      balGb: balParsed.gb,
      lineFg: Array.from(schedParsed.lineFg).sort(),
      lineGb: Array.from(schedParsed.lineGb).sort(),
      styleFg: masterParsed.styleFg,
      styleGb: masterParsed.styleGb
    };
    return cache;
  }

  function detectAndSplitCombined(workbook){
    // Try to detect sheets that look like master/schedule/balance
    let sheets = workbook.SheetNames;
    let found = {master:null, schedule:null, balance:null};
    for(let name of sheets){
      let sheet = workbook.Sheets[name];
      let aoa = sheetToAOA(sheet);
      if (!aoa || aoa.length===0) continue;
      let headers = (aoa[0]||[]).map(h=> h==null?'':String(h).trim());
      let hasItemNo = headers.includes('ITEM_NO');
      let hasProdCat = headers.includes('PRODUCT_CATEGORY');
      let hasLineCode = headers.includes('LINE_CODE');
      let hasPlanItem = headers.includes('PLAN_ITEM');
      let hasItemCode = headers.includes('ITEM_CODE');
      let hasBalQty = headers.includes('BALANCE_QTY');
      if (hasItemNo && hasProdCat) found.master = name;
      else if (hasLineCode && hasPlanItem) found.schedule = name;
      else if (hasItemCode && hasBalQty) found.balance = name;
    }
    return found;
  }

  async function loadFromFiles(files){
    // files: array of File objects
    // Try to classify
    let masterFile=null, schedFile=null, balFile=null;
    let combinedWb=null;
    // First, read all workbooks
    let workbooks = [];
    for(let f of files){
      let data = await f.arrayBuffer();
      let wb = XLSX.read(data, {type:'array'});
      workbooks.push({file:f, wb});
      // Try detect if this single file is combined with 3 sheets
      let split = detectAndSplitCombined(wb);
      if (split.master && split.schedule && split.balance){
        // Combined file
        combinedWb = wb;
        // Extract individual
        // We'll use same workbook but with single sheets
        let masterWb = {SheetNames:[split.master], Sheets:{[split.master]: wb.Sheets[split.master]}};
        let schedWb = {SheetNames:[split.schedule], Sheets:{[split.schedule]: wb.Sheets[split.schedule]}};
        let balWb = {SheetNames:[split.balance], Sheets:{[split.balance]: wb.Sheets[split.balance]}};
        return loadFromWorkbooks(masterWb, schedWb, balWb);
      }
    }
    // Classify by filename
    function classifyByName(name){
      let low=name.toLowerCase();
      if (low.includes('master') || low.includes('料号')) return 'master';
      if (low.includes('sched') || low.includes('排产')) return 'schedule';
      if (low.includes('bal') || low.includes('boh') || low.includes('结存')) return 'balance';
      return null;
    }
    for(let {file, wb} of workbooks){
      let cls = classifyByName(file.name);
      // Also try header detection for single-sheet files
      let sheet = wb.Sheets[wb.SheetNames[0]];
      let aoa = sheetToAOA(sheet);
      if (!aoa || aoa.length===0) continue;
      let headers = (aoa[0]||[]).map(h=> h==null?'':String(h).trim());
      if (headers.includes('ITEM_NO') && headers.includes('PRODUCT_CATEGORY')) cls='master';
      else if (headers.includes('LINE_CODE') && headers.includes('PLAN_ITEM')) cls='schedule';
      else if (headers.includes('ITEM_CODE') && headers.includes('BALANCE_QTY')) cls='balance';
      if (cls==='master') masterFile=wb;
      else if (cls==='schedule') schedFile=wb;
      else if (cls==='balance') balFile=wb;
    }
    if (!masterFile || !schedFile || !balFile){
      // Try to use first 3 as fallback if still missing
      if (workbooks.length>=3 && !masterFile){
        // try to assign by order if not classified
        // Use header detection again
        for(let {wb} of workbooks){
          if (!masterFile){
            let aoa = sheetToAOA(wb.Sheets[wb.SheetNames[0]]);
            let headers=(aoa[0]||[]).map(h=> String(h||'').trim());
            if (headers.includes('ITEM_NO')) masterFile=wb;
          }
        }
      }
      // If still missing, try to find any that can be used
      if (!masterFile || !schedFile || !balFile){
        let missing = [];
        if (!masterFile) missing.push('料号主表');
        if (!schedFile) missing.push('排产结果表');
        if (!balFile) missing.push('结存表');
        throw new Error('Missing files: '+missing.join(', ')+' — please select 3 files (master/schedule/balance) or a combined file with 3 sheets');
      }
    }
    return loadFromWorkbooks(masterFile, schedFile, balFile);
  }

  // Global export
  global.IOReportEngine = {
    toDatetime,
    getColDefs,
    buildReportsForGroup,
    getMeta,
    loadFromWorkbooks,
    loadFromFiles,
    detectAndSplitCombined
  };

})(window);
