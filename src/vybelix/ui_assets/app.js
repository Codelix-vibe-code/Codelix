const state = { snapshot: null, activeView: "dashboard" };
const titles = {
  dashboard: ["Dashboard", "Vue réelle du projet Vybelix"],
  chat: ["Chat", "Décris une demande ; le Planner ne part qu’après validation du formulaire"],
  tasks: ["Tasks", "Tâches réellement enregistrées dans la progression"],
  agents: ["Agents", "Progression calculée depuis les tâches et opérations persistées"],
  models: ["Models", "Routes configurées — disponibilité non testée"],
  files: ["Files", "Arborescence locale filtrée des secrets"],
  changes: ["Changes", "Propositions réellement enregistrées"],
  terminal: ["Terminal", "Commandes autorisées et résultats persistés"],
  verification: ["Verification", "Résultats réellement enregistrés"],
  git: ["Git", "Branche, état du workspace et commits réels"],
  history: ["History", "Événements persistés par le moteur"],
  settings: ["Settings", "Configuration non secrète du projet"]
};
const byId = (id) => document.getElementById(id);

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}

function renderDashboard(snapshot) {
  const host = byId("view-content");
  host.replaceChildren();
  const grid = node("div", "data-grid");
  const tasks = snapshot.tasks;
  const completed = tasks.by_status.done || 0;
  const attention = (tasks.by_status.needs_review || 0) + (tasks.by_status.blocked || 0);
  const checks = snapshot.verification;
  const latestCheck = checks.latest;
  const cards = [
    ["Tâches", tasks.total, `${completed} terminée(s)`],
    ["À examiner", attention, "bloquées ou en revue"],
    ["Fichiers du projet", snapshot.project.file_count, "hors dossiers de dépendances"],
    ["Vérifications", checks.total, latestCheck ? (latestCheck.status === "passed" ? "dernière réussie" : "dernière en échec") : "aucune enregistrée"]
  ];
  for (const [label, value, detail] of cards) {
    const metric = node("div", "metric");
    metric.append(node("span", "", label), node("strong", "", value), node("small", "metric-detail", detail));
    grid.append(metric);
  }
  host.append(grid);

  const stateSection = node("section", "section-card");
  stateSection.append(node("h2", "", "État du projet"));
  const stateList = node("div", "route-list");
  const gitState = snapshot.git.available ? (snapshot.git.dirty ? "Modifications présentes" : "Propre") : "Non disponible";
  const verificationState = latestCheck ? `${latestCheck.status} · ${latestCheck.task_id}` : "Aucune vérification enregistrée";
  for (const [label, value] of [["Projet", "État local lisible"], ["Git", `${gitState}${snapshot.git.branch ? ` · ${snapshot.git.branch}` : ""}`], ["Dernière vérification", verificationState]]) {
    const row = node("div", "route-row");
    row.append(node("span", "", label), node("strong", "", value));
    stateList.append(row);
  }
  stateSection.append(stateList);
  host.append(stateSection);

  const activitySection = node("section", "section-card");
  activitySection.append(node("h2", "", "Activité récente enregistrée"));
  const activityList = node("div", "route-list");
  if (!snapshot.activity.length) {
    activityList.append(node("p", "muted", "Aucune vérification n’est enregistrée dans la progression du projet."));
  } else {
    for (const event of snapshot.activity) {
      const row = node("div", "route-row");
      const label = event.status === "passed" ? "Vérification réussie" : event.status === "timeout" ? "Vérification expirée" : "Vérification échouée";
      row.append(node("span", "", `${label} · ${event.task_id}`));
      row.append(node("span", "route-state", event.execution_id));
      activityList.append(row);
    }
  }
  activitySection.append(activityList);
  host.append(activitySection);

  const section = node("section", "section-card");
  section.append(node("h2", "", "Routage configuré"));
  const list = node("div", "route-list");
  if (!snapshot.routes.length) {
    list.append(node("p", "muted", "Aucun modèle n’est configuré dans le projet."));
  } else {
    for (const route of snapshot.routes) {
      const row = node("div", "route-row");
      row.append(node("strong", "", `${route.role} · ${route.provider}:${route.model}`));
      row.append(node("span", "route-state", "non vérifié"));
      list.append(row);
    }
  }
  section.append(list);
  host.append(section);

  const note = node("section", "empty-state dashboard-note");
  note.append(node("div", "empty-mark", "⌘"), node("h2", "", "Données issues de l’état local"));
  note.append(node("p", "", "Les tâches, propositions, vérifications et opérations sont lues depuis le projet. Aucun modèle ni aucune commande n’est lancé au chargement : chaque action reste déclenchée explicitement."));
  host.append(note);
}

function section(title) {
  const element = node("section", "section-card");
  element.append(node("h2", "", title));
  return element;
}

function row(label, value) {
  const element = node("div", "route-row");
  element.append(node("span", "", label), node("strong", "", value ?? "—"));
  return element;
}

function renderChat(snapshot, host) {
  const formSection = section("Nouvelle demande · Planner");
  const form = node("form", "chat-form");
  const input = node("textarea", "chat-input");
  input.placeholder = "Décris ce que tu veux faire dans le projet…";
  input.rows = 4;
  input.maxLength = 20000;
  input.setAttribute("aria-label", "Demande de développement");
  const submit = node("button", "primary-action", "Analyser et proposer un plan");
  submit.type = "submit";
  form.append(input, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!input.value.trim()) return;
    await runOperation("/api/plan", { request: input.value.trim() }, host, "Planner en cours…");
  });
  formSection.append(form);
  host.append(formSection);

  const plan = snapshot.pending_plan;
  const planCard = section(plan ? (plan.approved ? "Plan approuvé" : "Plan en attente d’approbation") : "Plan");
  if (!plan) {
    planCard.append(node("p", "muted", "Aucun plan n’est enregistré pour ce projet."));
  } else {
    planCard.append(node("p", "", plan.request_summary));
    planCard.append(node("p", "muted", `${plan.tasks.length} tâche(s) · chemins affectés : ${[...new Set(plan.tasks.flatMap((task) => task.affected_paths || []))].length}`));
    plan.tasks.forEach((task) => {
      const item = node("article", "detail-card");
      item.append(node("strong", "", `${task.id || "Tâche"} · ${task.title || "Sans titre"}`));
      item.append(node("p", "muted", `${task.role || "Rôle non précisé"} · dépendances : ${(task.dependencies || []).join(", ") || "aucune"}`));
      if (task.description) item.append(node("p", "", task.description));
      (task.acceptance_criteria || []).forEach((criterion) => item.append(node("small", "muted", `✓ ${criterion}`)));
      planCard.append(item);
    });
    if (!plan.approved) {
      const actions = node("div", "action-row");
      const approve = node("button", "primary-action", "Approuver le plan");
      const reject = node("button", "secondary-action", "Refuser le plan");
      approve.type = reject.type = "button";
      approve.addEventListener("click", async () => {
        if (!window.confirm(`Approuver ${plan.tasks.length} tâche(s) et les ajouter à la progression ?`)) return;
        const result = await postAction("/api/approve-plan", {});
        if (result) { showNotice(`${result.task_ids.length} tâche(s) ajoutée(s) à la progression.`); await refreshSnapshot(); }
      });
      reject.addEventListener("click", async () => {
        if (!window.confirm("Refuser et supprimer le plan en attente ? Aucune tâche ne sera ajoutée.")) return;
        if (await postAction("/api/reject-plan", {})) { showNotice("Plan refusé."); await refreshSnapshot(); }
      });
      actions.append(reject, approve);
      planCard.append(actions);
    }
  }
  host.append(planCard);
  const traces = (snapshot.history || []).filter((event) => ["plan_created", "proposal_created"].includes(event.type) && event.routing?.length);
  if (traces.length) {
    const last = traces[traces.length - 1];
    const routing = section("Dernier routage constaté");
    last.routing.forEach((attempt) => routing.append(row(`${attempt.provider}:${attempt.model}`, `${attempt.outcome}${attempt.status_code ? ` · HTTP ${attempt.status_code}` : ""}`)));
    host.append(routing);
  }
}

function renderTasks(snapshot, host) {
  const board = node("div", "task-board");
  const columns = [["todo", "À faire"], ["in_progress", "En cours"], ["review", "À examiner"], ["done", "Terminées"], ["other", "Autres états"]];
  const planned = new Map((snapshot.pending_plan?.tasks || []).map((task) => [task.id, task]));
  const proposalIds = new Set(snapshot.proposals.map((item) => item.task_id));
  const taskStates = new Map(snapshot.tasks_detail.map((task) => [task.id, task.status]));
  columns.forEach(([key, label]) => {
    const column = node("section", "task-column");
    column.append(node("h2", "", label));
    const matching = snapshot.tasks_detail.filter((task) => key === "review" ? ["needs_review", "blocked"].includes(task.status) : key === "other" ? ["interrupted", "cancelled"].includes(task.status) : task.status === key);
    if (!matching.length) column.append(node("p", "muted", "Aucune tâche"));
    matching.forEach((task) => {
      const planTask = planned.get(task.id) || task;
      const card = node("article", "task-card");
      card.append(node("span", "task-id", task.id), node("strong", "", task.title), node("span", "task-status", task.status));
      if (planTask.role) card.append(node("small", "muted", `Agent : ${planTask.role}`));
      if (planTask.description) card.append(node("p", "muted", planTask.description));
      if (task.dependencies.length) card.append(node("small", "muted", `Dépendances : ${task.dependencies.join(", ")}`));
      if ((task.files_modified || []).length) card.append(node("small", "muted", `Fichiers modifiés : ${task.files_modified.join(", ")}`));
      if (planTask.affected_paths?.length) card.append(node("small", "muted", `Fichiers prévus : ${planTask.affected_paths.join(", ")}`));
      (task.acceptance_criteria || []).forEach((criterion) => card.append(node("small", "muted", `✓ ${criterion}`)));
      const ready = task.dependencies.every((dependency) => taskStates.get(dependency) === "done");
      if (snapshot.pending_plan?.approved && ["coder", "tester"].includes(task.role) && ["todo", "needs_review"].includes(task.status) && !proposalIds.has(task.id) && ready) {
        const generate = node("button", "secondary-action", `Générer proposition ${task.role}`);
        generate.type = "button";
        generate.addEventListener("click", async () => {
          if (!window.confirm(`Lancer l’agent ${task.role} pour ${task.id} ? Cela appelle un modèle configuré et produit une proposition sans modifier les fichiers.`)) return;
          const result = await runOperation("/api/code", { task_id: task.id }, host, `${task.role} en cours…`);
          if (result) showView("changes");
        });
        card.append(generate);
      }
      column.append(card);
    });
    board.append(column);
  });
  host.append(board);
}

function renderAgents(snapshot, host) {
  const panel = section("Équipe d’agents · progression réelle");
  const grid = node("div", "agent-grid");
  const agents = snapshot.agents || [];
  if (!agents.length) panel.append(node("p", "muted", "Aucun état d’agent disponible."));
  agents.forEach((agent) => {
    const card = node("article", `agent-card agent-${agent.role}`);
    card.dataset.role = agent.role;
    const identity = node("div", "agent-identity");
    identity.append(node("span", "agent-orb", ""));
    const title = node("div", "agent-title");
    title.append(node("h2", "", agent.name), node("p", "", agent.subtitle));
    identity.append(title);
    const status = node("span", "agent-status", agent.status);
    const detail = node("p", "agent-detail", agent.detail);
    card.append(identity, status, detail);
    if (agent.current_task) card.append(node("p", "agent-current", `En cours · ${agent.current_task}`));
    const progressHead = node("div", "agent-progress-head");
    progressHead.append(node("span", "", "Progression"), node("strong", "", `${agent.progress}%`));
    const progress = node("div", "agent-progress");
    progress.setAttribute("role", "progressbar");
    progress.setAttribute("aria-label", `Progression de ${agent.name}`);
    progress.setAttribute("aria-valuemin", "0"); progress.setAttribute("aria-valuemax", "100");
    progress.setAttribute("aria-valuenow", String(agent.progress));
    const fill = node("span", "agent-progress-fill");
    fill.style.width = `${Math.max(0, Math.min(100, agent.progress))}%`;
    progress.append(fill);
    card.append(progressHead, progress);
    grid.append(card);
  });
  panel.append(grid);
  panel.append(node("p", "muted agent-footnote", "Les barres comptent uniquement les tâches achevées et les vérifications enregistrées. Une proposition à examiner reste en attente."));
  host.append(panel);
}

function renderModels(snapshot, host) {
  const models = section("Routage configuré et résultats constatés");
  if (!snapshot.routes.length) models.append(node("p", "muted", "Aucune route configurée."));
  const attempts = (snapshot.history || []).flatMap((event) => event.routing || []);
  snapshot.routes.forEach((route) => {
    const history = attempts.filter((attempt) => attempt.provider === route.provider && attempt.model === route.model);
    const successes = history.filter((attempt) => attempt.outcome === "success").length;
    const errors = history.filter((attempt) => attempt.outcome !== "success").length;
    const stateLabel = successes ? `Réponse constatée ${successes} fois dans l’historique` : errors ? `Échec constaté ${errors} fois` : "Accès au compte non vérifié";
    models.append(row(`${route.role} · candidat ${route.order}`, `${route.provider}:${route.model} · ${stateLabel}`));
  });
  host.append(models);
  host.append(noteCard("Disponibilité des modèles", "La présence dans le routage ne confirme pas l’accès au compte. Seules les réponses réelles enregistrées sont marquées comme constatées."));
}

function renderFiles(snapshot, host) {
  const listing = section("Explorateur du projet · lecture contrôlée");
  const search = node("input", "file-search");
  search.type = "search"; search.placeholder = "Filtrer les chemins…"; search.setAttribute("aria-label", "Filtrer les fichiers du projet");
  const list = node("div", "file-list");
  const preview = node("section", "file-preview");
  function update(filter = "") {
    list.replaceChildren();
    const shown = snapshot.files.filter((entry) => entry.path.toLowerCase().includes(filter.toLowerCase()));
    if (!shown.length) list.append(node("p", "muted", "Aucun chemin correspondant."));
    shown.forEach((entry) => {
      const line = node(entry.type === "file" ? "button" : "div", `file-entry ${entry.type}`);
      if (entry.type === "file") { line.type = "button"; line.addEventListener("click", async () => {
        const response = await fetch(`/api/files/${encodeURIComponent(entry.path)}`, { headers: { Accept: "application/json" }, cache: "no-store" });
        const data = await response.json();
        preview.replaceChildren();
        if (!response.ok) preview.append(node("p", "error-text", data.error || "Aperçu impossible."));
        else { preview.append(node("h3", "", data.path)); const pre = node("pre", "file-content", data.content); preview.append(pre); }
        preview.hidden = false;
      }); }
      line.append(node("span", "", entry.type === "directory" ? "▸" : "·"), node("span", "", entry.path));
      if (entry.type === "file") line.append(node("small", "muted", entry.size_bytes == null ? "" : `${entry.size_bytes} o`));
      list.append(line);
    });
  }
  search.addEventListener("input", () => update(search.value));
  update();
  preview.hidden = true;
  listing.append(search, list, preview);
  listing.append(node("p", "muted", `${snapshot.files.length} entrée(s) listée(s), maximum 500. Les secrets, dépendances, propositions et sauvegardes sont exclus. Les fichiers texte UTF-8 de moins de 200 Ko peuvent être consultés.`));
  host.append(listing);
}

function renderChanges(snapshot, host) {
  if (!snapshot.proposals.length) { host.append(noteCard("Aucune proposition enregistrée", "Les propositions Coder apparaîtront ici après leur génération depuis une tâche approuvée.")); return; }
  snapshot.proposals.forEach((proposal) => {
    const card = section(`Proposition · ${proposal.task_id}`);
    card.append(node("p", "muted", `${proposal.files.length} fichier(s) proposés. Consulte le diff complet avant de décider.`));
    proposal.files.forEach((file) => card.append(row(file.operation, file.path)));
    const display = node("div", "diff-container");
    const view = node("button", "secondary-action", "Afficher le diff"); view.type = "button";
    view.addEventListener("click", async () => {
      display.replaceChildren(node("p", "muted", "Chargement du diff…")); display.hidden = false;
      try {
        const response = await fetch(`/api/proposals/${encodeURIComponent(proposal.task_id)}`, { headers: { Accept: "application/json" }, cache: "no-store" });
        const diff = await response.json();
        if (!response.ok) throw new Error(diff.error || "Diff indisponible.");
        display.replaceChildren(node("p", "", diff.summary));
        (diff.notes || []).forEach((note) => display.append(node("p", "muted", note)));
        diff.files.forEach((file) => { display.append(node("h3", "", `${file.path} · +${file.added} −${file.removed}`)); display.append(node("pre", "diff-content", file.diff || "Aucune différence textuelle.")); });
        const actions = node("div", "action-row");
        const reject = node("button", "secondary-action", "Refuser la proposition"); reject.type = "button";
        reject.addEventListener("click", async () => { if (window.confirm(`Refuser la proposition ${proposal.task_id} ? Aucun fichier ne sera modifié.`) && await postAction("/api/reject-proposal", { task_id: proposal.task_id })) { showNotice("Proposition refusée ; fichiers inchangés."); await refreshSnapshot(); } });
        const apply = node("button", "primary-action", "Approuver et appliquer"); apply.type = "button";
        apply.addEventListener("click", async () => {
          const paths = diff.files.map((file) => file.path);
          if (!window.confirm(`Appliquer ${paths.length} fichier(s) ?\n${paths.join("\n")}\n\nL’Execution Manager créera d’abord une sauvegarde contrôlée. Aucun commit Git ne sera créé.`)) return;
          const result = await postAction("/api/apply", { task_id: proposal.task_id, approved: true, approved_paths: paths, approved_hashes: diff.approved_hashes });
          if (result) { showNotice(`Modifications appliquées. Point de retour : ${result.rollback_id}`); await refreshSnapshot(); }
        });
        actions.append(reject, apply); display.append(actions);
      } catch (error) { display.replaceChildren(node("p", "error-text", error.message)); }
    });
    card.append(view, display); host.append(card);
  });
}

function renderVerification(snapshot, host) {
  const commands = section("Commandes autorisées");
  if (!snapshot.allowed_commands.length) commands.append(node("p", "muted", "Aucune commande de vérification autorisée dans la configuration."));
  snapshot.allowed_commands.forEach((command) => commands.append(node("code", "command-line", command)));
  host.append(commands);
  const runnable = snapshot.tasks_detail.filter((task) => task.status === "in_progress");
  if (runnable.length && snapshot.allowed_commands.length) {
    const run = section("Lancer une vérification contrôlée");
    const taskSelect = node("select", "select-control");
    runnable.forEach((task) => { const option = node("option", "", `${task.id} · ${task.title}`); option.value = task.id; taskSelect.append(option); });
    const commandSelect = node("select", "select-control");
    snapshot.allowed_commands.forEach((command) => { const option = node("option", "", command); option.value = command; commandSelect.append(option); });
    const execute = node("button", "primary-action", "Exécuter la commande autorisée"); execute.type = "button";
    execute.addEventListener("click", async () => {
      if (!window.confirm(`Exécuter la commande configurée ci-dessous pour ${taskSelect.value} ?\n${commandSelect.value}`)) return;
      const result = await runOperation("/api/verify", { task_id: taskSelect.value, command: commandSelect.value }, host, "Vérification en cours…");
      if (result) showNotice(result.exit_code === 0 ? "Vérification réussie." : `Vérification terminée avec le code ${result.exit_code}.`);
    });
    run.append(taskSelect, commandSelect, execute); host.append(run);
  }
  const results = section("Résultats persistés");
  const history = snapshot.verification_history || [];
  if (!history.length) results.append(node("p", "muted", "Aucun résultat de vérification enregistré."));
  history.forEach(({ task_id, records }) => records.forEach((record) => {
    const status = record.exit_code == null ? "Délai dépassé" : record.exit_code === 0 ? "Réussie" : `Échec · code ${record.exit_code}`;
    results.append(row(`${task_id} · ${status}`, `${record.command || "Commande inconnue"} · ${record.duration_seconds ?? "—"} s`));
    if (record.summary) results.append(node("p", "muted result-summary", record.summary));
  }));
  host.append(results);
}

function renderGitHistory(snapshot, host) {
  const git = section("Dépôt Git · consultation seule");
  git.append(row("Branche", snapshot.git_details.branch || (snapshot.git_details.available ? "détachée" : "Git indisponible")));
  git.append(row("Workspace", snapshot.git_details.available ? (snapshot.git_details.dirty ? "Modifications présentes" : "Propre") : "Non disponible"));
  host.append(git);
  const commits = section("Commits récents");
  if (!snapshot.git_details.commits.length) commits.append(node("p", "muted", "Aucun commit disponible dans le dépôt."));
  snapshot.git_details.commits.forEach((commit) => commits.append(row(`${commit.hash} · ${commit.date}`, commit.subject)));
  host.append(commits);
  const events = section("Historique des opérations Vybelix");
  const history = [...(snapshot.history || [])].reverse();
  if (!history.length) events.append(node("p", "muted", "Aucune opération Vybelix persistée."));
  const labels = { plan_created: "Plan généré", plan_approved: "Plan approuvé", plan_rejected: "Plan refusé", proposal_created: "Proposition générée", proposal_rejected: "Proposition refusée", changes_applied: "Modifications appliquées", verification_completed: "Vérification exécutée" };
  history.forEach((event) => {
    const taskLabel = (event.task_ids || []).join(", ");
    const detail = event.files?.join(", ") || event.command || (event.routing || []).map((attempt) => `${attempt.provider}:${attempt.model} ${attempt.outcome}`).join(" → ") || taskLabel || event.rollback_id || "Opération enregistrée";
    events.append(row(`${labels[event.type] || event.type}${taskLabel ? ` · ${taskLabel}` : ""}`, `${event.timestamp} · ${detail}`));
  });
  host.append(events);
}

function renderSettings(snapshot, host) {
  const safe = section("Configuration active · lecture seule");
  safe.append(row("Projet", snapshot.project.name));
  safe.append(row("Routes", `${snapshot.routes.length} candidat(s) configuré(s)`));
  safe.append(row("Timeout modèle", `${snapshot.runtime.request_timeout_seconds ?? "non défini"} s`));
  safe.append(row("Taille maximale de fichier", `${snapshot.runtime.max_file_bytes ?? "non définie"} octets`));
  safe.append(row("Corrections maximales", snapshot.runtime.correction_attempts ?? "non définies"));
  safe.append(row("Commandes autorisées", snapshot.allowed_commands.length));
  safe.append(node("p", "muted", "Les noms de clés API ne sont jamais affichés ici. Les routes modèle se modifient dans vybelix.toml après choix explicite."));
  host.append(safe);
  const appearance = section("Apparence locale");
  const label = node("label", "setting-label", "Intensité des halos néon");
  const select = node("select", "select-control");
  [["soft", "Discrète"], ["balanced", "Équilibrée"], ["vivid", "Renforcée"]].forEach(([value, text]) => { const option = node("option", "", text); option.value = value; select.append(option); });
  select.value = localStorage.getItem("codelix.ui.glow") || "balanced";
  select.addEventListener("change", () => { document.documentElement.dataset.glow = select.value; localStorage.setItem("codelix.ui.glow", select.value); });
  document.documentElement.dataset.glow = select.value;
  label.append(select); appearance.append(label);
  const motion = node("label", "setting-label", "Animations");
  const motionSelect = node("select", "select-control");
  [["system", "Préférence système"], ["reduced", "Réduites"], ["full", "Normales"]].forEach(([value, text]) => { const option = node("option", "", text); option.value = value; motionSelect.append(option); });
  motionSelect.value = localStorage.getItem("codelix.ui.motion") || "system";
  motionSelect.addEventListener("change", () => { document.documentElement.dataset.motion = motionSelect.value; localStorage.setItem("codelix.ui.motion", motionSelect.value); });
  document.documentElement.dataset.motion = motionSelect.value;
  motion.append(motionSelect); appearance.append(motion); host.append(appearance);
  const security = section("Sécurité de cette interface");
  security.append(row("Serveur", "Loopback uniquement"));
  security.append(row("Écritures", "Execution Manager après approbation explicite"));
  security.append(row("Commandes", "Liste d’autorisation seulement, confirmation avant exécution"));
  security.append(row("Valeurs des clés", "Jamais lues ni affichées par l’interface"));
  host.append(security);
}

function noteCard(title, text) {
  const card = node("section", "empty-state dashboard-note");
  card.append(node("div", "empty-mark", "◇"), node("h2", "", title), node("p", "", text));
  return card;
}

function showNotice(message, error = false) {
  let toast = byId("action-notice");
  if (!toast) { toast = node("div", "action-notice"); toast.id = "action-notice"; toast.setAttribute("role", "status"); toast.setAttribute("aria-live", "polite"); document.body.append(toast); }
  toast.textContent = message; toast.classList.toggle("error", error); toast.classList.add("visible");
  window.clearTimeout(showNotice.timer); showNotice.timer = window.setTimeout(() => toast.classList.remove("visible"), 6500);
}

async function postAction(path, payload) {
  try {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(payload), cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Erreur HTTP ${response.status}`);
    return data;
  } catch (error) { showNotice(error.message || "Action impossible.", true); return null; }
}

async function refreshSnapshot() {
  try { const response = await fetch("/api/state", { headers: { Accept: "application/json" }, cache: "no-store" }); if (!response.ok) throw new Error("État local indisponible"); renderState(await response.json()); }
  catch (error) { showNotice(error.message, true); }
}

async function runOperation(path, payload, host, label) {
  const status = node("p", "operation-status", label); host.append(status);
  const started = await postAction(path, payload);
  if (!started) { status.remove(); return null; }
  let operation;
  try {
    for (let elapsed = 0; elapsed < 900000; elapsed += 900) {
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      if (elapsed > 0 && elapsed % 2700 === 0) {
        const stateResponse = await fetch("/api/state", { headers: { Accept: "application/json" }, cache: "no-store" });
        if (stateResponse.ok) renderState(await stateResponse.json());
      }
      const response = await fetch(`/api/operations/${encodeURIComponent(started.operation_id)}`, { headers: { Accept: "application/json" }, cache: "no-store" });
      operation = await response.json();
      if (!response.ok) throw new Error(operation.error || "Opération introuvable.");
      status.textContent = operation.status === "queued" ? `${label} · en file…` : operation.status === "running" ? `${label} · traitement…` : operation.status;
      if (operation.status === "done") break;
      if (operation.status === "failed") throw new Error(operation.error?.message || "L’opération a échoué.");
    }
    if (!operation || operation.status !== "done") throw new Error("Délai d’attente UI dépassé ; vérifie l’état avant de relancer.");
    state.lastRouting = operation.result?.routing || [];
    status.remove();
    await refreshSnapshot();
    return operation.result;
  } catch (error) { status.remove(); showNotice(error.message || "Opération échouée.", true); await refreshSnapshot(); return null; }
}

function renderConnectedView(view, snapshot) {
  const host = byId("view-content");
  const [title, subtitle] = titles[view] || titles.dashboard;
  byId("view-title").textContent = title;
  byId("view-subtitle").textContent = subtitle;
  host.replaceChildren();
  if (view === "dashboard") renderDashboard(snapshot, host);
  else if (view === "chat") renderChat(snapshot, host);
  else if (view === "tasks") renderTasks(snapshot, host);
  else if (view === "agents") renderAgents(snapshot, host);
  else if (view === "models") renderModels(snapshot, host);
  else if (view === "files") renderFiles(snapshot, host);
  else if (view === "changes") renderChanges(snapshot, host);
  else if (["terminal", "verification"].includes(view)) renderVerification(snapshot, host);
  else if (["git", "history"].includes(view)) renderGitHistory(snapshot, host);
  else if (view === "settings") renderSettings(snapshot, host);
  else renderDashboard(snapshot, host);
}

function renderState(snapshot) {
  state.snapshot = snapshot;
  byId("project-name").textContent = snapshot.project.name;
  byId("context-project").textContent = snapshot.project.name;
  byId("context-project-id").textContent = `Identifiant ${snapshot.project.id}`;
  const git = snapshot.git;
  const branch = git.available ? (git.branch || "détachée") : "non disponible";
  byId("branch-name").textContent = branch;
  byId("context-branch").textContent = `Branche ${branch}`;
  byId("context-git").textContent = !git.available ? "Non disponible" : git.dirty ? "Modifications présentes" : "Propre";
  byId("status-git").textContent = `Git ${git.available ? (git.dirty ? "modifié" : "propre") : "indisponible"}`;
  byId("context-routes").textContent = `${snapshot.routes.length} candidat(s)`;
  byId("status-task-count").textContent = `${snapshot.tasks.total} tâche(s)`;
  const attention = (snapshot.tasks.by_status.needs_review || 0) + (snapshot.tasks.by_status.blocked || 0);
  for (const agent of snapshot.agents || []) {
    const status = byId(`agent-${agent.role}-state`);
    if (status) status.textContent = agent.status;
    const dot = byId(`agent-${agent.role}-dot`);
    if (dot) dot.classList.toggle("active", ["En cours", "Actif"].includes(agent.status));
  }
  const badge = byId("attention-count");
  badge.textContent = attention;
  badge.hidden = attention === 0;
  const connection = byId("connection-state");
  connection.classList.add("connected");
  connection.querySelector("span").textContent = "Moteur local connecté";
  renderConnectedView(state.activeView, snapshot);
}

function showView(view) {
  state.activeView = view;
  document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  if (state.snapshot) renderConnectedView(view, state.snapshot);
  else renderConnectedView(view, { tasks_detail: [], files: [], proposals: [], routes: [], agents: [], history: [], operations: [], verification_history: [], allowed_commands: [], activity: [], runtime: {}, tasks: { total: 0, by_status: {} }, verification: { total: 0, latest: null }, project: {}, git: {}, git_details: {}, capabilities: {} });
  byId("workspace").focus({ preventScroll: true });
}

document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});
byId("open-settings").addEventListener("click", () => showView("settings"));

fetch("/api/state", { headers: { Accept: "application/json" }, cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error("État local indisponible");
    return response.json();
  })
  .then(renderState)
  .catch(() => {
    byId("connection-state").querySelector("span").textContent = "État local indisponible";
    const host = byId("view-content");
    host.replaceChildren();
    const error = node("div", "empty-state");
    error.append(node("div", "empty-mark", "!"), node("h2", "", "Impossible de lire l’état du projet"));
    error.append(node("p", "", "Vérifie que Vybelix est lancé depuis la racine du projet et que sa configuration locale est valide."));
    host.append(error);
  });

// The navigation and context column widths persist locally on this device.
(function enablePanelResizing() {
  const shell = document.querySelector(".app-shell");
  const handles = document.querySelectorAll(".resize-handle");
  const limits = { sidebar: { min: 160, max: 360, initial: 224 }, context: { min: 220, max: 420, initial: 286 } };
  const storageKey = "codelix.ui.panel-widths.v1";
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(storageKey) || "{}"); } catch { saved = {}; }

  function applyWidth(name, width) {
    const rule = limits[name];
    const value = Math.round(Math.max(rule.min, Math.min(rule.max, width)));
    const property = name === "sidebar" ? "--sidebar-width" : "--context-width";
    shell.style.setProperty(property, `${value}px`);
    const handle = document.querySelector(`[data-resize="${name}"]`);
    if (handle) {
      handle.setAttribute("aria-valuemin", rule.min);
      handle.setAttribute("aria-valuemax", rule.max);
      handle.setAttribute("aria-valuenow", value);
    }
    saved[name] = value;
    try { localStorage.setItem(storageKey, JSON.stringify(saved)); } catch { /* Storage may be unavailable. */ }
  }

  for (const name of Object.keys(limits)) {
    const width = Number(saved[name]);
    applyWidth(name, Number.isFinite(width) ? width : limits[name].initial);
  }

  handles.forEach((handle) => {
    const name = handle.dataset.resize;
    const rule = limits[name];
    let pointerStart = null;
    handle.addEventListener("pointerdown", (event) => {
      if (window.matchMedia("(max-width: 760px)").matches || event.button !== 0) return;
      pointerStart = { x: event.clientX, width: shell.getBoundingClientRect().width ? parseFloat(getComputedStyle(shell).getPropertyValue(name === "sidebar" ? "--sidebar-width" : "--context-width")) || rule.initial : rule.initial };
      shell.classList.add("is-resizing");
      handle.classList.add("dragging");
      handle.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    handle.addEventListener("pointermove", (event) => {
      if (!pointerStart) return;
      const direction = name === "sidebar" ? 1 : -1;
      applyWidth(name, pointerStart.width + (event.clientX - pointerStart.x) * direction);
    });
    const finish = () => { pointerStart = null; shell.classList.remove("is-resizing"); handle.classList.remove("dragging"); };
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
    handle.addEventListener("keydown", (event) => {
      const current = Number(handle.getAttribute("aria-valuenow")) || rule.initial;
      const step = event.shiftKey ? 32 : 12;
      let next = current;
      if (event.key === "ArrowLeft") next += name === "sidebar" ? -step : step;
      else if (event.key === "ArrowRight") next += name === "sidebar" ? step : -step;
      else if (event.key === "Home") next = rule.min;
      else if (event.key === "End") next = rule.max;
      else return;
      event.preventDefault();
      applyWidth(name, next);
    });
    handle.addEventListener("dblclick", () => applyWidth(name, rule.initial));
  });
})();
const savedGlow = localStorage.getItem("codelix.ui.glow");
if (savedGlow) document.documentElement.dataset.glow = savedGlow;
const savedMotion = localStorage.getItem("codelix.ui.motion");
if (savedMotion) document.documentElement.dataset.motion = savedMotion;
