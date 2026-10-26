/* Private investigation controls. Results are data; public saving uses the existing review gates. */
(() => {
  "use strict";
  window.ReplicaRunner = { mount({ context, request, onFinding, onSkill }) {
    const $ = id => document.getElementById(id), status = message => { $("runnerStatus").textContent = message; };
    const key = c => c ? c.wallet + ":" + c.asset + ":" + c.token : "";
    let loading = false, runners = [], jobs = [], pairKnown = null;
    const post = async (action, body = {}, expected = key(context())) => {
      const c = context();
      if (!c || key(c) !== expected) throw new Error("Wallet or replica changed. Reopen the runner controls.");
      const route = action.startsWith("hosted/") ? "api/rea/" + action.slice(7) : "api/runner/" + action;
      const result = await request(route, { token: c.token, asset: c.asset, ...body });
      if (key(context()) !== expected) throw new Error("Wallet or replica changed; result hidden.");
      return result;
    };
    const button = (label, action) => {
      const b = document.createElement("button"); b.className = "btn ghost"; b.textContent = label;
      b.onclick = async () => { b.disabled = true; try { await action(); } catch (e) { status(e.message); } finally { b.disabled = false; } };
      return b;
    };
    function clear() {
      runners = []; jobs = []; $("runnerSelect").textContent = ""; $("runnerJobs").textContent = "";
      $("runnerPairCode").textContent = ""; $("runnerStart").disabled = true;
      if ($("reaHostedJobs")) { $("reaHostedJobs").textContent=""; $("reaHostedFile").value=""; $("reaHostedConsent").checked=false; }
    }
    let painted = "";
    async function refresh() {
      const c = context(), current = key(c);
      if (current !== painted) { clear(); painted = current; }
      if (!c || loading) return;
      loading = true;
      try {
        await refreshHosted(current);
        const data = await post("list", {}, current);
        runners = data.runners; jobs = data.jobs;
        if (pairKnown && runners.some(r => !pairKnown.has(r.id))) { $("runnerPairCode").textContent = "Computer paired. The one-time code has been consumed."; pairKnown = null; }
        const select = $("runnerSelect"), previous = select.value; select.textContent = "";
        for (const r of runners) {
          const o = document.createElement("option"); o.value = r.id;
          o.textContent = r.name + " · " + (r.online ? "ready" : "offline") + (r.target.file ? " · " + r.target.label + "/" + r.target.file : " · select a file locally");
          select.appendChild(o);
        }
        if (runners.some(r => r.id === previous)) select.value = previous;
        $("runnerStart").disabled = !runners.some(r => r.id === select.value && r.online && r.target.file);
        $("runnerDisconnect").disabled = !runners.length;
        const out = $("runnerJobs"); out.textContent = jobs.length ? "" : "No investigations yet. Pair a computer and choose a source file there.";
        for (const job of jobs) {
          const entry = document.createElement("details"), title = document.createElement("summary"), description = document.createElement("p");
          title.textContent = job.question + " — " + ({ queued: "waiting for runner", running: "check your runner for local approval", review: "ready for your review", cancelled: "cancelled", failed: "stopped" }[job.state] || job.state);
          description.className = "note"; description.textContent = job.target.label + "/" + job.target.file + " · " + (job.error || "Private to this host. Nothing is in public memory yet.");
          entry.append(title, description);
          if (job.result.report) { const report = document.createElement("pre"); report.className = "note rea-preview skill-preview"; report.textContent = job.result.report; entry.appendChild(report); }
          if (job.result.finding) entry.appendChild(button("review finding before remembering", async () => { if (key(context()) !== current) throw new Error("Wallet changed."); await onFinding(JSON.stringify(job.result.finding)); }));
          if (job.has_package) entry.appendChild(button("review code, evidence and tests", async () => { const data = await post("get", { job_id: job.id }, current); if (!data.result.package_json) throw new Error("This result was cleared. Refresh the tasks."); await onSkill(data.result.package_json); }));
          if (["queued", "running", "review"].includes(job.state)) entry.appendChild(button("cancel and clear private result", async () => { await post("cancel", { job_id: job.id }, current); await refresh(); }));
          out.appendChild(entry);
        }
      } catch (e) { status(e.message); }
      finally { loading = false; }
    }
    $("runnerPair").onclick = async () => {
      $("runnerPair").disabled = true;
      try { const offer = await post("offer"); pairKnown = new Set(runners.map(r => r.id)); $("runnerPairCode").textContent = "One-time code (10 minutes):\n" + offer.code + "\n\nPaste this into the runner on your computer. Keep it private."; status("Pairing authorizes this computer for this replica only. It cannot sign memory entries or move tokens."); }
      catch (e) { status(e.message); } finally { $("runnerPair").disabled = false; }
    };
    $("runnerSelect").onchange = () => { $("runnerStart").disabled = !runners.some(r => r.id === $("runnerSelect").value && r.online && r.target.file); };
    $("runnerStart").onclick = async () => {
      $("runnerStart").disabled = true;
      try { await post("enqueue", { runner_id: $("runnerSelect").value, question: $("runnerQuestion").value.trim() }); status("Task queued. Approve the inspection on your computer, then review its summary here."); await refresh(); }
      catch (e) { status(e.message); } finally { $("runnerSelect").onchange(); }
    };
    $("runnerDisconnect").onclick = async () => {
      try { await post("revoke", { runner_id: $("runnerSelect").value }); $("runnerPairCode").textContent = ""; status("Runner disconnected. Its private results have been cleared."); await refresh(); } catch (e) { status(e.message); }
    };
    $("runnerRefresh").onclick = refresh;
    async function refreshHosted(current=key(context())) {
      if (!$("reaHostedJobs") || !context()) return;
      try {
        const data=await post("hosted/list",{},current),out=$("reaHostedJobs");
        $("reaHostedStatus").textContent=data.available ? "REA is ready. Choose the sample or upload a source file." : "REA worker is temporarily unavailable; existing results are still readable.";
        if(out.querySelector("details[open]")) return;
        out.textContent=data.jobs.length ? "" : "No website investigations yet.";
        for(const job of data.jobs) {
          const entry=document.createElement("details"),title=document.createElement("summary"),note=document.createElement("p");
          title.textContent=job.question+" — "+({queued:"queued for REA",running:"REA is inspecting",review:"findings ready",failed:"inspection stopped",cancelled:"cleared"}[job.state]||job.state);
          note.className="note";note.textContent=job.target.file+" · "+(job.error||"Private findings. Nothing saved to public memory.");entry.append(title,note);
          if(job.result.report){const report=document.createElement("pre");report.className="rea-preview note";report.textContent=job.result.report;entry.append(report);}
          if(job.result.finding)entry.append(button("review finding before remembering",async()=>{if(key(context())!==current)throw new Error("Wallet changed.");await onFinding(JSON.stringify(job.result.finding));}));
          if(["queued","running","review"].includes(job.state))entry.append(button("cancel and clear",async()=>{await post("hosted/cancel",{job_id:job.id},current);entry.open=false;await refreshHosted(current);}));
          out.append(entry);
        }
      }catch(e){$("reaHostedStatus").textContent=e.message;}
    }
    if($("reaHostedStart")) {
      $("reaHostedTarget").onchange=()=>{$("reaHostedFile").hidden=$("reaHostedTarget").value!=="upload";$("reaHostedConsent").checked=false;};
      $("reaHostedFile").onchange=()=>{$("reaHostedConsent").checked=false;};
      $("reaHostedRefresh").onclick=()=>{for(const entry of $("reaHostedJobs").querySelectorAll("details"))entry.open=false;return refreshHosted();};
      $("reaHostedStart").onclick=async()=>{
        const current=key(context());$("reaHostedStart").disabled=true;
        try {
          if(!$("reaHostedConsent").checked)throw new Error("Approve sending the source for inspection first.");
          const body={sample:$("reaHostedTarget").value==="sample",question:$("reaHostedQuestion").value.trim(),consent:true};
          if(!body.sample){const file=$("reaHostedFile").files[0];if(!file)throw new Error("Choose a source file.");if(file.size>256000)throw new Error("Choose a file of 256 KB or smaller.");body.filename=file.name;body.source=await file.text();}
          await post("hosted/start",body,current);$("reaHostedConsent").checked=false;
          for(const entry of $("reaHostedJobs").querySelectorAll("details"))entry.open=false;
          await refreshHosted(current);$("reaHostedStatus").textContent="Your replica queued the REA inspection. Findings will appear here; no local runner is needed.";
        }catch(e){$("reaHostedStatus").textContent=e.message;}finally{$("reaHostedStart").disabled=false;}
      };
    }
    // Keep an open result stable while the host reads it. Explicit refresh remains available.
    setInterval(() => { if (context() && !document.hidden && !$("runnerJobs").querySelector("details[open]")) refresh(); }, 10000);
    return { refresh, clear };
  } };
})();
