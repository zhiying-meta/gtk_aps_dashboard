/**
 * Inventory Dashboard Shared Renderer
 * Extracted for reuse between standalone Inventory Dashboard and IO and BOH's Inventory tab
 * Exposes window.InventoryRenderer with pure functions
 */
window.InventoryRenderer = (() => {
  function esc(s) { return s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : ''; }

  function buildFullTree(pn, inventory, bomChildren, timeBuckets, visited) {
    if (visited.has(pn)) return null;
    visited.add(pn);
    const node = { key: pn, partNumber: pn };
    const inv = inventory[pn] || {};
    for (const tb of timeBuckets) node[tb] = inv[tb] ?? null;
    const kids = (bomChildren[pn] || []).filter(c => inventory[c] !== undefined || (bomChildren[c] && bomChildren[c].length>0));
    if (kids.length > 0) {
      node.children = kids.map(c => buildFullTree(c, inventory, bomChildren, timeBuckets, new Set(visited))).filter(Boolean);
    }
    return node;
  }

  function getTreeRoots(inventory, bomChildren, bomParents) {
    const allKeys = Object.keys(inventory);
    const skKeys = allKeys.filter(k => k.startsWith('SK-')).sort();
    if (skKeys.length > 0) return skKeys;
    const allChildrenSet = new Set();
    for (const childs of Object.values(bomChildren)) {
      for (const c of childs) allChildrenSet.add(c);
    }
    const roots = allKeys.filter(k => !allChildrenSet.has(k)).sort();
    if (roots.length > 0) return roots;
    return allKeys.sort();
  }

  function hasNegativeInSubtree(node, timeBuckets) {
    for (const tb of timeBuckets) {
      const v = node[tb];
      if (v !== null && v !== undefined && Number(v) < 0) return true;
    }
    if (node.children) {
      for (const ch of node.children) {
        if (hasNegativeInSubtree(ch, timeBuckets)) return true;
      }
    }
    return false;
  }

  function hasMatchingDescendant(node, searchLower) {
    if (!node.children) return false;
    for (const ch of node.children) {
      if (ch.partNumber.toLowerCase().includes(searchLower)) return true;
      if (hasMatchingDescendant(ch, searchLower)) return true;
    }
    return false;
  }

  function flattenTree(treeData, expandedSet, searchLower, onlyNeg, timeBuckets) {
    const rows = [];
    function walk(nodes, depth) {
      for (const n of nodes) {
        let include = true;
        if (searchLower) {
          include = n.partNumber.toLowerCase().includes(searchLower);
        }
        if (onlyNeg && include) {
          let hasNeg = false;
          for (const tb of timeBuckets) {
            const v = n[tb];
            if (v !== null && v !== undefined && Number(v) < 0) { hasNeg = true; break; }
          }
          if (!hasNeg) {
            include = hasNegativeInSubtree(n, timeBuckets);
          }
        }
        if (include) {
          rows.push({ ...n, _depth: depth, _expanded: expandedSet.has(n.key), _hasChildren: !!(n.children && n.children.length) });
        } else {
          if (searchLower) {
            if (hasMatchingDescendant(n, searchLower)) {
              rows.push({ ...n, _depth: depth, _expanded: true, _hasChildren: !!(n.children && n.children.length) });
              if (n.children) walk(n.children, depth + 1);
              continue;
            }
          }
        }
        if (n.children && expandedSet.has(n.key)) {
          walk(n.children, depth + 1);
        }
      }
    }
    walk(treeData, 0);
    return rows;
  }

  function pnColor(pn) {
    if (pn.startsWith('SK-')) return 'pn-sk';
    if (pn.startsWith('GB-') || pn.startsWith('SUB-') || pn.startsWith('SUB')) return 'pn-gb';
    return 'pn-other';
  }

  /**
   * Render inventory table into container
   * @param {HTMLElement} container - container element
   * @param {Object} dashboardData - {timeBuckets, inventory, bomChildren, bomParents, hasChildren}
   * @param {Object} state - {expanded: Set, selectedSKUs: [], searchText: string, showOnlyNegative: bool}
   * @param {Object} callbacks - {onToggle: fn(pn), onExpandAll, onCollapseAll, onSearch: fn(text), onSKUFilter: fn(selected), onClearFilter, onExport, onOnlyNegToggle}
   * @param {String} prefix - ID prefix for elements to avoid collisions (e.g., 'io' or 'inv')
   */
  function renderTable(container, dashboardData, state, callbacks, prefix = 'inv') {
    const { inventory, bomChildren, hasChildren, timeBuckets, bomParents } = dashboardData;
    const expanded = state.expanded || new Set();
    const selectedSKUs = state.selectedSKUs || [];
    const searchText = state.searchText || "";
    const showOnlyNegative = state.showOnlyNegative || false;

    const skuOptionsAll = Object.keys(inventory).filter(pn => pn.startsWith('SK-')).sort();
    const allSKUs = skuOptionsAll.length > 0 ? skuOptionsAll : Object.keys(inventory).sort();

    // Build tree
    let roots = getTreeRoots(inventory, bomChildren||{}, bomParents||{});
    if (selectedSKUs.length > 0) {
      roots = roots.filter(pn => selectedSKUs.includes(pn));
    }
    const treeData = roots.map(pn => buildFullTree(pn, inventory, bomChildren||{}, timeBuckets, new Set())).filter(Boolean);
    const flatRows = flattenTree(treeData, expanded, searchText.toLowerCase(), showOnlyNegative, timeBuckets);

    // Year grouping
    const yearGroups = {};
    for (const tb of timeBuckets) {
      const year = tb.slice(0,4);
      if (!yearGroups[year]) yearGroups[year] = [];
      yearGroups[year].push(tb);
    }
    const yearKeys = Object.keys(yearGroups).sort();

    // Consistent with IO and BOH toolbar style: panels-row + panel + panel-label + filter-row
    container.innerHTML = `
      <div class="toolbar" style="border:none;padding:8px 0;margin-bottom:8px;background:transparent">
        <div class="panels-row" style="display:flex;gap:12px;align-items:stretch;flex-wrap:wrap">
          <div class="panel" style="flex:1;min-width:320px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:8px 12px">
            <div class="panel-label" style="font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;margin-bottom:6px;letter-spacing:0.4px">🔍 Filters — ${timeBuckets.length} time buckets × ${Object.keys(inventory).length} materials</div>
            <div class="filter-row" style="display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin-top:6px">
              <div class="filter-group" style="display:flex;flex-direction:column;gap:2px;min-width:180px">
                <label style="font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase">Search PN</label>
                <input type="text" id="${prefix}-search" class="filter-input inv-search-input" placeholder="Part No..." value="${esc(searchText)}" style="width:100%;padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px">
              </div>
              <div class="filter-group" style="display:flex;flex-direction:column;gap:2px;min-width:200px">
                <label style="font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase">SKU Category <span style="font-size:10px;color:#94a3b8">(${allSKUs.length})</span></label>
                <select id="${prefix}-sku-select" class="filter-input inv-sku-select" multiple size="1" title="Multi-select SKU filter — Hold Ctrl/Cmd to select multiple" style="width:100%;padding:5px 8px;border:1px solid #cbd5e1;border-radius:5px;font-size:12px;min-width:200px;max-width:320px">
                  ${allSKUs.map(sku => `<option value="${esc(sku)}" ${selectedSKUs.includes(sku) ? 'selected' : ''}>${esc(sku)}</option>`).join('')}
                </select>
              </div>
              <div class="filter-group" style="display:flex;flex-direction:column;gap:4px;min-width:120px">
                <label style="font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase">Options</label>
                <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:#475569"><input type="checkbox" id="${prefix}-chk-neg" ${showOnlyNegative ? 'checked' : ''}> Negative only</label>
              </div>
              <div class="filter-group" style="display:flex;flex-direction:row;gap:6px;align-items:flex-end">
                <button id="${prefix}-btn-apply-sku" class="btn btn-sm btn-outline" style="padding:4px 10px">Apply Filter</button>
                <button id="${prefix}-btn-clear-sku" class="btn btn-sm btn-outline" style="padding:4px 10px">✕ Clear</button>
              </div>
            </div>
          </div>
          <div class="panel" style="min-width:200px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:8px 12px">
            <div class="panel-label" style="font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;margin-bottom:6px">Stats</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center">
              <span class="tag tag-blue" style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe">SK- FG (${allSKUs.length})</span>
              <span class="tag tag-orange" style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#fffbeb;color:#92400e;border:1px solid #fde68a">Time Buckets: ${timeBuckets.length}</span>
              <span style="font-size:11px;color:#64748b">Showing: ${flatRows.length} rows</span>
            </div>
          </div>
          <div class="panel" style="min-width:180px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;padding:8px 12px">
            <div class="panel-label" style="font-size:11px;font-weight:600;color:#475569;text-transform:uppercase;margin-bottom:6px">Actions</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
              <button id="${prefix}-btn-expand-all" class="btn btn-sm btn-outline" style="padding:4px 10px">▼ Expand All</button>
              <button id="${prefix}-btn-collapse-all" class="btn btn-sm btn-outline" style="padding:4px 10px">▶ Collapse All</button>
              <button id="${prefix}-btn-export" class="btn btn-sm" style="padding:4px 10px;background:#0f172a;border-color:#0f172a">📥 Export JSON</button>
            </div>
          </div>
        </div>
      </div>
      <div class="inv-table-wrap" style="overflow:auto;background:#fff;border-radius:8px;border:1px solid #e2e8f0;max-height:calc(100vh - 280px)">
        <table class="inv-compact-table" style="width:max-content;min-width:100%;border-collapse:collapse;font-size:12px">
          <thead>
            <tr class="inv-year-row" style="background:#e2e8f0">
              <th style="position:sticky;left:0;z-index:4;top:0;min-width:220px;text-align:left;padding:4px 6px;background:#e2e8f0;border-bottom:2px solid #cbd5e1;font-size:12px">Material PN</th>
              ${yearKeys.map(year => `<th colSpan="${yearGroups[year].length}" style="position:sticky;top:0;z-index:1;text-align:center;padding:4px 6px;background:#e2e8f0;border-bottom:2px solid #cbd5e1">${esc(year)}</th>`).join('')}
            </tr>
            <tr class="inv-date-row">
              <th style="position:sticky;left:0;z-index:4;top:26px;min-width:220px;height:36px;background:#f1f5f9;border-bottom:1px solid #e2e8f0"></th>
              ${timeBuckets.map(tb => {
                const parts = tb.split(' ');
                const d = parts[0] || '';
                const s = parts[1] || '';
                // Support both Chinese 夜班 and English Night for night shift icon; keep parsing compatibility
                const isNight = s === '夜班' || s.toLowerCase().includes('night') || s === 'N';
                const short = d.slice(5) + ' ' + (isNight ? '☾' : '☀');
                return `<th style="position:sticky;top:26px;z-index:1;width:52px;height:56px;text-align:center;padding:4px 6px;background:#f1f5f9;border-bottom:1px solid #e2e8f0;font-size:11px"><span class="inv-rot" style="display:inline-block;transform:rotate(-30deg);transform-origin:bottom left;white-space:nowrap;font-size:10px" title="${esc(tb)}">${esc(short)}</span></th>`;
              }).join('')}
            </tr>
          </thead>
          <tbody>
            ${flatRows.map(row => {
              return `
              <tr>
                <td style="position:sticky;left:0;z-index:1;background:#fff;padding:3px 8px;padding-left:${12 + row._depth * 20}px;border-bottom:1px solid #f1f5f9;text-align:left;font-family:monospace;font-size:11px;white-space:nowrap">
                  <button class="inv-expand-btn ${row._expanded ? 'expanded' : ''} ${!row._hasChildren ? 'leaf' : ''}" data-pn="${esc(row.key)}" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border:1px solid #cbd5e1;border-radius:4px;background:#fff;cursor:pointer;font-size:10px;margin-right:6px;${!row._hasChildren ? 'visibility:hidden' : ''}">${row._hasChildren ? (row._expanded ? '▼' : '▶') : ''}</button>
                  <span class="inv-pn-name ${pnColor(row.partNumber)}" style="${pnColor(row.partNumber)==='pn-sk' ? 'color:#2563eb;font-weight:600' : pnColor(row.partNumber)==='pn-gb' ? 'color:#059669' : 'color:#475569'}" title="${esc(row.partNumber)}">${esc(row.partNumber)}</span>
                </td>
                ${timeBuckets.map(tb => {
                  const val = row[tb];
                  if (val === null || val === undefined) return '<td style="padding:3px 8px;border-bottom:1px solid #f1f5f9;text-align:right;color:#cbd5e1">-</td>';
                  const num = Number(val);
                  const isNeg = num < 0;
                  return `<td class="${isNeg ? 'inv-neg-cell' : ''}" style="padding:3px 8px;border-bottom:1px solid #f1f5f9;text-align:right;white-space:nowrap;${isNeg ? 'background:#fef2f2;color:#dc2626;font-weight:700' : ''}" title="${esc(row.partNumber)} — ${esc(tb)}: ${num.toLocaleString()}">${num.toLocaleString()}</td>`;
                }).join('')}
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>
      <div style="margin-top:8px;font-size:11px;color:#94a3b8">
        💡 Click <b>[▶]</b> to expand child materials (BOM subtree) · Red highlight is <b>Ending_OnHand &lt; 0</b> negative inventory · Balance pre-calculated, display only
      </div>
    `;

    // Bind events if callbacks provided
    if (callbacks) {
      const bind = (id, event, handler) => {
        const el = document.getElementById(id);
        if (el && handler) el.addEventListener(event, handler);
      };
      bind(`${prefix}-search`, 'input', (e) => callbacks.onSearch && callbacks.onSearch(e.target.value));
      bind(`${prefix}-btn-apply-sku`, 'click', () => {
        const sel = document.getElementById(`${prefix}-sku-select`);
        const selected = sel ? Array.from(sel.selectedOptions).map(o => o.value) : [];
        callbacks.onSKUFilter && callbacks.onSKUFilter(selected);
      });
      bind(`${prefix}-btn-clear-sku`, 'click', () => callbacks.onClearFilter && callbacks.onClearFilter());
      bind(`${prefix}-chk-neg`, 'change', (e) => callbacks.onOnlyNegToggle && callbacks.onOnlyNegToggle(e.target.checked));
      bind(`${prefix}-btn-expand-all`, 'click', () => callbacks.onExpandAll && callbacks.onExpandAll());
      bind(`${prefix}-btn-collapse-all`, 'click', () => callbacks.onCollapseAll && callbacks.onCollapseAll());
      bind(`${prefix}-btn-export`, 'click', () => callbacks.onExport && callbacks.onExport());

      container.querySelectorAll('.inv-expand-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const pn = e.currentTarget.dataset.pn;
          if (pn && callbacks.onToggle) callbacks.onToggle(pn);
        });
      });
    }

    return { flatRows, treeData };
  }

  return {
    esc,
    buildFullTree,
    getTreeRoots,
    flattenTree,
    hasNegativeInSubtree,
    hasMatchingDescendant,
    pnColor,
    renderTable
  };
})();
