'use strict';
window.etaMaster=(()=>{
  const {sourceLabel='Veri',enabledKey='collection_enabled'}=window.etaMasterConfig||{};
  let rows=[],query='',plant='',filter='',page=1,pastePreview=null;
  const size=50;
  const action=(label,name,css='')=>`<button class="button ${css}" data-master-action="${name}">${label}</button>`;
  async function render(seq){
    const result=await api('/api/suppliers');
    if(seq!==state.renderSeq)return;
    rows=result.rows;
    $('#content').innerHTML=heading('Master data','Hangi GSDB çekilsin, kim ilgilensin? Tek liste.',action('Liste yapıştır','paste')+action('GSDB ekle','add','primary'))+
      `<section class="card master-card"><div class="table-toolbar"><div class="search-field">${icon('search')}<input id="master-search" placeholder="GSDB veya sorumlu ara…" value="${esc(query)}"></div><select id="master-plant" class="filter-select" aria-label="Tesis"><option value="">Tüm tesisler</option>${Object.keys(state.plants).sort().map(p=>`<option ${p===plant?'selected':''}>${esc(p)}</option>`).join('')}</select><select id="master-filter" class="filter-select" aria-label="Kapsam"><option value="">Tümü</option><option value="enabled" ${filter==='enabled'?'selected':''}>${esc(sourceLabel)} açık</option><option value="disabled" ${filter==='disabled'?'selected':''}>${esc(sourceLabel)} kapalı</option><option value="missing" ${filter==='missing'?'selected':''}>Sorumlu eksik</option></select></div><div class="table-footer" id="master-summary"></div><div class="table-wrap"><table><thead><tr><th>Tesis</th><th>GSDB</th><th>${esc(sourceLabel)} çekilsin</th><th>Sorumlu</th><th></th></tr></thead><tbody id="master-body"></tbody></table></div><div class="table-footer"><span id="master-count"></span><div class="pagination">${action('‹','prev')}<span id="master-page"></span>${action('›','next')}</div></div></section><p class="hint">Kaydettiğin kapsam bir sonraki ${esc(sourceLabel)} çekiminde kullanılır. Geçmiş ekranlar silinmez. Buradaki değişiklikler terminale veri yazmaz.</p>`;
    draw();
  }
  function draw(){
    const filtered=rows.filter(r=>(!plant||r.plant===plant)&&(!query||`${r.gsdb} ${r.owner}`.toLocaleLowerCase('tr').includes(query.toLocaleLowerCase('tr')))&&(!filter||(filter==='enabled'&&r[enabledKey]!==false)||(filter==='disabled'&&r[enabledKey]===false)||(filter==='missing'&&!r.owner)));
    page=Math.max(1,Math.min(page,Math.ceil(filtered.length/size)||1));
    $('#master-summary').textContent=`${fmt(rows.length)} tesis + GSDB · ${fmt(rows.filter(r=>r[enabledKey]!==false).length)} ${esc(sourceLabel)} açık · ${fmt(rows.filter(r=>!r.owner).length)} sorumlu eksik`;
    $('#master-body').innerHTML=filtered.slice((page-1)*size,page*size).map(r=>`<tr data-master-plant="${esc(r.plant)}" data-master-gsdb="${esc(r.gsdb)}"><td><span class="plant-tag">${esc(r.plant)}</span></td><td><strong>${esc(r.gsdb)}</strong></td><td><label><input type="checkbox" name="enabled" ${r[enabledKey]!==false?'checked':''} aria-label="${esc(r.gsdb)} ${esc(sourceLabel)} çekilsin"> Çek</label></td><td><input name="owner" value="${esc(r.owner)}" maxlength="100" placeholder="Sorumlu adı" aria-label="${esc(r.gsdb)} sorumlusu"></td><td>${action('Kaydet','save','small')}</td></tr>`).join('')||'<tr><td colspan="5">Eşleşen kayıt yok.</td></tr>';
    $('#master-count').textContent=`${fmt(filtered.length)} kayıt`;
    $('#master-page').textContent=`${page} / ${Math.max(1,Math.ceil(filtered.length/size))}`;
    $('[data-master-action="prev"]').disabled=page<=1;
    $('[data-master-action="next"]').disabled=page*size>=filtered.length;
  }
  document.addEventListener('input',event=>{
    if(event.target.id==='master-paste-text'){resetPaste();return;}
    if(event.target.id!=='master-search')return;
    query=event.target.value;page=1;draw();
  });
  document.addEventListener('change',event=>{
    if(['master-paste-plant','master-paste-enabled'].includes(event.target.id)){resetPaste();return;}
    if(!['master-plant','master-filter'].includes(event.target.id))return;
    if(event.target.id==='master-plant')plant=event.target.value;else filter=event.target.value;
    page=1;draw();
  });
  function resetPaste(){
    pastePreview=null;
    const result=$('#master-paste-result'),apply=$('[data-master-action="paste-apply"]');
    if(result)result.innerHTML='';if(apply)apply.disabled=true;
  }
  function pasteBody(){return {text:$('#master-paste-text').value,plant:$('#master-paste-plant').value,new_enabled:$('#master-paste-enabled').checked};}
  function pasteDialog(){
    pastePreview=null;
    dialog('Sorumlu listesini yapıştır','Önce ayrıştır ve kontrol et, sonra kaydet.',
      `<div class="form-grid"><label>Uygulanacak tesis<select id="master-paste-plant"><option value="">Tüm mevcut tesis eşleşmeleri</option>${Object.keys(state.plants).sort().map(p=>`<option ${plant===p?'selected':''}>${esc(p)}</option>`).join('')}</select></label><label class="profile-check"><input id="master-paste-enabled" type="checkbox" checked><span>Yeni GSDB'lerde ${esc(sourceLabel)} çekilsin</span></label></div><p class="hint">Excel'den GSDB ve sorumlu sütunlarını birlikte kopyala veya her satırı “GSDB - Sorumlu” biçiminde yaz. Yeni GSDB eklemek için tesis seç. Kayıtlı GSDB'lerin ${esc(sourceLabel)} seçimi korunur.</p><textarea id="master-paste-text" rows="9" maxlength="300000" aria-label="GSDB ve sorumlu listesi" placeholder="GSDB - Sorumlu" style="width:100%;resize:vertical"></textarea><div id="master-paste-result" class="master-paste-result" aria-live="polite"></div>`,
      button('Vazgeç','close-dialog')+action('Ayrıştır ve önizle','paste-preview')+action('Eşleşmeleri kaydet','paste-apply','primary').replace('<button ','<button disabled '));
  }
  function showPastePreview(result){
    const counts=result.counts,labels={ADD:'Yeni',UPDATE:'Güncellenecek',SAME:'Aynı'};
    $('#master-paste-result').innerHTML=`<p><strong>${counts.ADD} yeni · ${counts.UPDATE} güncellenecek · ${counts.SAME} aynı</strong>${result.duplicates?` · ${result.duplicates} aynı tekrar birleştirildi`:''}</p>`+
      (result.errors.length?`<div class="workflow-blocker"><strong>${result.errors.length} hata · kayıt yapılmayacak</strong><ul>${result.errors.slice(0,20).map(error=>`<li>${error.line?'Satır '+error.line+': ':''}${esc(error.message)}</li>`).join('')}</ul>${result.errors.length>20?'<p>Diğer hatalar için ilk hataları düzeltip yeniden önizleyin.</p>':''}</div>`:'')+
      (result.changes.length?`<div class="table-wrap" style="max-height:32vh;overflow:auto"><table><thead><tr><th>Tesis</th><th>GSDB</th><th>Eski sorumlu</th><th>Yeni sorumlu</th><th>Durum</th></tr></thead><tbody>${result.changes.map(row=>`<tr><td>${esc(row.plant)}</td><td>${esc(row.gsdb)}</td><td>${esc(row.old_owner||'—')}</td><td>${esc(row.owner)}</td><td>${labels[row.status]}</td></tr>`).join('')}</tbody></table></div>`:'');
    const apply=$('[data-master-action="paste-apply"]');apply.disabled=!result.can_apply;
    apply.textContent=`${counts.ADD+counts.UPDATE} eşleşmeyi kaydet`;
  }
  document.addEventListener('click',async event=>{
    const btn=event.target.closest('[data-master-action]');if(!btn)return;
    try{
      const name=btn.dataset.masterAction;
      if(name==='paste'){pasteDialog();return;}
      if(name==='paste-preview'){
        btn.disabled=true;
        const body=pasteBody();pastePreview=null;
        $('[data-master-action="paste-apply"]').disabled=true;
        const result=await api('/api/suppliers/paste/preview',{method:'POST',body});
        if(!$('#master-paste-text')||JSON.stringify(body)!==JSON.stringify(pasteBody()))return;
        pastePreview={...body,revision:result.revision};showPastePreview(result);return;
      }
      if(name==='paste-apply'){
        if(btn.disabled||!pastePreview)return;
        btn.disabled=true;
        const result=await api('/api/suppliers/paste/apply',{method:'POST',body:pastePreview});
        pastePreview=null;closeDialog();await refreshSummary();if(state.view==='suppliers')await render(state.renderSeq);
        toast(`${result.counts.ADD} yeni kayıt, ${result.counts.UPDATE} sorumlu güncellemesi kaydedildi.`);return;
      }
      if(name==='prev'||name==='next'){page+=name==='next'?1:-1;draw();return;}
      if(name==='add'){
        dialog('GSDB ekle','Tesis + GSDB tek kayıt olarak tutulur.',`<div class="form-grid"><label>Tesis<select id="master-new-plant">${Object.keys(state.plants).sort().map(p=>`<option>${esc(p)}</option>`).join('')}</select></label><label>GSDB<input id="master-new-gsdb" maxlength="5" placeholder="5 harf / rakam"></label><label>Sorumlu<input id="master-new-owner" maxlength="100"></label><label><input id="master-new-enabled" type="checkbox" checked> ${esc(sourceLabel)} çekilsin</label></div>`,button('Vazgeç','close-dialog')+action('Kaydet','create','primary'));
        return;
      }
      btn.disabled=true;
      if(name==='create'){
        await api('/api/suppliers',{method:'POST',body:{plant:$('#master-new-plant').value,gsdb:$('#master-new-gsdb').value,owner:$('#master-new-owner').value,[enabledKey]:$('#master-new-enabled').checked}});
        closeDialog();await refreshSummary();await render(state.renderSeq);toast('Master data kaydı eklendi.');
      }
      if(name==='save'){
        const row=btn.closest('tr');
        const updated=await api(`/api/suppliers/${encodeURIComponent(row.dataset.masterPlant)}/${encodeURIComponent(row.dataset.masterGsdb)}`,{method:'PATCH',body:{owner:row.querySelector('[name="owner"]').value,[enabledKey]:row.querySelector('[name="enabled"]').checked}});
        rows=rows.map(r=>r.plant===updated.plant&&r.gsdb===updated.gsdb?updated:r);
        await refreshSummary();draw();toast('Kapsam ve sorumlu kaydedildi.');
      }
    }catch(error){if(btn.dataset.masterAction==='paste-apply')pastePreview=null;toast(error.message,'error');}finally{btn.disabled=btn.dataset.masterAction==='paste-apply'&&!pastePreview;}
  });
  return {render};
})();
