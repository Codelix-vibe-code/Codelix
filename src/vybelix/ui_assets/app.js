const state = { snapshot: null, activeView: "dashboard", chatDraft: "", apiKeySession: null, apiKeySetupRequired: true, tourIndex: null, tourKeyHandler: null, tourResizeHandler: null };
const tourStorageKey = "vybelix.ui.product-tour.v1";
const tourSteps = [
  { view: "dashboard", selector: '[data-view="dashboard"]', title: "Accueil", text: "Retrouve ici l’état général du projet : tâches, vérifications, fichiers et activité récente." },
  { view: "chat", selector: '[data-view="chat"]', title: "Assistant", text: "Décris ce que tu veux construire. Vybelix prépare un plan que tu peux examiner avant de l’approuver." },
  { view: "agents", selector: '[data-view="agents"]', title: "Agents", text: "Suis le Planner, le Coder et le Tester : leur rôle, leur état et l’avancement du projet." },
  { view: "verification", selector: '[data-view="verification"]', title: "Vérification", text: "Consulte les commandes autorisées et leurs résultats pour repérer rapidement les erreurs." },
  { view: "skills", selector: '[data-view="skills"]', title: "Tes skills", text: "Crée et gère tes extensions locales. Leur code reste désactivé tant qu’un sandbox isolé n’est pas disponible." },
  { view: "settings", selector: '[data-view="settings"]', title: "Paramètres", text: "Configure les options locales du projet et ouvre le gestionnaire de clés API depuis cette section." },
  { view: "settings", selector: ".level-preference", title: "Ton niveau", text: "Choisis le degré d’accompagnement de Vybelix. Tu peux changer ce niveau ici quand tu veux." },
  { view: "settings", selector: ".api-key-settings", title: "API Keys · coffre-fort local", text: "Ajoute ici tes clés de fournisseur, choisis un modèle parmi les recommandations et teste sa connexion. Les clés sont protégées dans le coffre local Vybelix." }
];
const titles = {
  dashboard: ["Accueil", "Vue d’ensemble du projet Vybelix"],
  chat: ["Assistant", "Décris ton idée et prépare un plan à examiner"],
  tasks: ["Tâches", "Un aperçu simple de ce qui reste à faire"],
  agents: ["Agents", "État et progression de chaque agent"],
  models: ["Modèles", "Modèles configurés pour le projet"],
  skills: ["Skills", "Parcourir, valider et gérer les extensions locales"],
  files: ["Fichiers", "Fichiers du projet"],
  changes: ["Modifications", "Propositions à examiner"],
  terminal: ["Terminal", "Commandes disponibles et résultats"],
  verification: ["Vérification", "Résultats des vérifications"],
  git: ["Git", "Branche et état du dépôt"],
  history: ["Historique", "Activité récente du projet"],
  settings: ["Paramètres", "Configuration du projet"]
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
  const home = node("section", "chat-home");
  const hero = node("div", "chat-hero");
  hero.append(node("span", "chat-eyebrow", "VYBELIX · ESPACE DE TRAVAIL"));
  hero.append(node("h2", "", "Que voulez-vous construire aujourd’hui ?"));
  hero.append(node("p", "chat-intro", "Décrivez votre idée. Vybelix préparera un plan que vous pourrez examiner avant de l’approuver."));

  const form = node("form", "chat-composer");
  const input = node("textarea", "chat-input");
  input.placeholder = "Message à Vybelix… Décrivez votre projet";
  input.value = state.chatDraft;
  input.addEventListener("input", () => { state.chatDraft = input.value; });
  input.rows = 3;
  input.maxLength = 20000;
  input.setAttribute("aria-label", "Demande de développement");
  const footer = node("div", "chat-composer-footer");
  footer.append(node("span", "chat-hint", "Le plan reste un brouillon jusqu’à votre approbation."));
  const submit = node("button", "chat-send", "↑");
  submit.type = "submit";
  submit.setAttribute("aria-label", "Préparer un plan");
  submit.title = "Préparer un plan";
  footer.append(submit);
  form.append(input, footer);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!input.value.trim()) { input.focus(); return; }
    const result = await runOperation("/api/plan", { request: input.value.trim() }, host, "Préparation du plan…");
    if (result) { state.chatDraft = ""; input.value = ""; }
  });
  hero.append(form);

  home.append(hero);
  host.append(home);

  const plan = snapshot.pending_plan;
  const latestPlanOperation = (snapshot.operations || []).find((operation) => operation.kind === "plan");
  const previousDraftAfterFailure = latestPlanOperation?.status === "failed" && Boolean(plan);
  const planTitle = previousDraftAfterFailure
    ? "Brouillon précédent · dernière tentative échouée"
    : plan ? (plan.approved ? "Plan approuvé" : "Plan à examiner") : "Plan récent";
  const planCard = section(planTitle);
  planCard.classList.add("chat-plan-section");
  if (previousDraftAfterFailure) {
    planCard.append(node("p", "muted", "La dernière tentative de planification a échoué. Le brouillon affiché provient d’une tentative précédente."));
  }
  if (!plan) {
    planCard.append(node("p", "muted", "Votre plan apparaîtra ici après l’analyse de votre demande."));
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
    const actions = node("div", "action-row");
    const reject = node("button", "secondary-action", plan.approved ? "Désapprouver le plan" : "Refuser le plan");
    reject.type = "button";
    reject.addEventListener("click", async () => {
      const prompt = plan.approved
        ? "Désapprouver ce plan et retirer ses tâches de la progression ? Possible uniquement si aucune tâche n’a commencé."
        : "Refuser et supprimer le plan en attente ? Aucune tâche ne sera ajoutée.";
      if (!window.confirm(prompt)) return;
      const result = await postAction("/api/reject-plan", {});
      if (result) {
        showNotice(result.approval_reverted ? "Plan désapprouvé ; ses tâches non commencées ont été retirées." : "Plan refusé.");
        await refreshSnapshot();
      }
    });
    actions.append(reject);
    if (!plan.approved) {
      const approve = node("button", "primary-action", "Approuver le plan");
      approve.type = "button";
      approve.addEventListener("click", async () => {
        if (!window.confirm(`Approuver ${plan.tasks.length} tâche(s) et les ajouter à la progression ?`)) return;
        const result = await postAction("/api/approve-plan", {});
        if (result) { showNotice(`${result.task_ids.length} tâche(s) ajoutée(s) à la progression.`); await refreshSnapshot(); }
      });
      actions.append(approve);
    }
    planCard.append(actions);
  }
  host.append(planCard);
  const traces = (snapshot.history || []).filter((event) => ["plan_created", "proposal_created"].includes(event.type) && event.routing?.length);
  if (traces.length) {
    const last = traces[traces.length - 1];
    const routing = section("Dernière activité des modèles");
    routing.classList.add("chat-plan-section");
    last.routing.forEach((attempt) => routing.append(row(`${attempt.provider}:${attempt.model}`, `${attempt.outcome}${attempt.status_code ? ` · HTTP ${attempt.status_code}` : ""}`)));
    host.append(routing);
  }
}
function renderTasks(snapshot, host) {
  const tasks = snapshot.tasks_detail || [];
  const statusCounts = snapshot.tasks?.by_status || {};
  const waiting = tasks.filter((task) => ["todo", "in_progress", "needs_review", "blocked"].includes(task.status));
  const completed = tasks.filter((task) => task.status === "done");
  const other = tasks.filter((task) => ["interrupted", "cancelled"].includes(task.status));
  const planned = new Map((snapshot.pending_plan?.tasks || []).map((task) => [task.id, task]));
  const proposalIds = new Set((snapshot.proposals || []).map((item) => item.task_id));
  const taskStates = new Map(tasks.map((task) => [task.id, task.status]));
  const labels = { todo: "À faire", in_progress: "En cours", needs_review: "À examiner", blocked: "Bloquée", done: "Terminée", interrupted: "Interrompue", cancelled: "Annulée" };

  const summary = node("div", "task-summary");
  [
    ["À faire", statusCounts.todo || 0],
    ["En cours", statusCounts.in_progress || 0],
    ["À examiner", (statusCounts.needs_review || 0) + (statusCounts.blocked || 0)],
    ["Terminées", statusCounts.done || 0]
  ].forEach(([label, count]) => {
    const item = node("div", "task-summary-item");
    item.append(node("strong", "", count), node("span", "", label));
    summary.append(item);
  });
  host.append(summary);

  function makeTaskCard(task) {
    const planTask = planned.get(task.id) || task;
    const card = node("article", "task-card task-card-compact");
    const heading = node("div", "task-card-heading");
    heading.append(node("strong", "", task.title || "Tâche sans titre"));
    heading.append(node("span", `task-status-pill status-${task.status}`, labels[task.status] || "Autre état"));
    card.append(heading);
    if (planTask.description) card.append(node("p", "task-description", planTask.description));

    const details = node("details", "task-more");
    details.append(node("summary", "", "Voir les détails"));
    const content = node("div", "task-more-content");
    content.append(node("small", "task-id", task.id));
    if (planTask.role) content.append(node("p", "muted", `Responsable : ${planTask.role}`));
    if (task.dependencies?.length) content.append(node("p", "muted", `Dépend de : ${task.dependencies.join(", ")}`));
    if (task.files_modified?.length) content.append(node("p", "muted", `Fichiers modifiés : ${task.files_modified.join(", ")}`));
    if (planTask.affected_paths?.length) content.append(node("p", "muted", `Fichiers prévus : ${planTask.affected_paths.join(", ")}`));
    (task.acceptance_criteria || []).forEach((criterion) => content.append(node("small", "task-criterion", `✓ ${criterion}`)));
    details.append(content);
    card.append(details);

    if (["blocked", "interrupted"].includes(task.status)) {
      const resume = node("button", "secondary-action task-action", "Reprendre la tâche");
      resume.type = "button";
      const readyToResume = (task.dependencies || []).every((dependency) => taskStates.get(dependency) === "done");
      resume.disabled = !readyToResume;
      resume.title = readyToResume ? "Remettre cette tâche en attente" : "Termine d’abord ses dépendances";
      resume.addEventListener("click", async () => {
        if (!window.confirm(`Remettre ${task.id} en attente ? Aucun agent ne sera lancé.`)) return;
        const result = await postAction("/api/resume", { task_id: task.id, approved: true });
        if (result) { showNotice("Tâche remise en attente. Lance-la explicitement lorsque tu le souhaites."); await refreshSnapshot(); }
      });
      card.append(resume);
    }

    const ready = (task.dependencies || []).every((dependency) => taskStates.get(dependency) === "done");
    if (snapshot.pending_plan?.approved && ["coder", "tester"].includes(task.role) && ["todo", "needs_review"].includes(task.status) && !proposalIds.has(task.id) && ready) {
      const generate = node("button", "secondary-action task-action", task.role === "tester" ? "Vérifier la tâche" : "Proposer du code");
      generate.type = "button";
      generate.addEventListener("click", async () => {
        if (!window.confirm(`Lancer l’agent ${task.role} pour ${task.id} ? Cela crée une proposition sans modifier les fichiers.`)) return;
        const result = await runOperation("/api/code", { task_id: task.id }, host, "Préparation en cours…");
        if (result) showView("changes");
      });
      card.append(generate);
    }
    return card;
  }

  const todoSection = section("À traiter");
  if (waiting.length) waiting.forEach((task) => todoSection.append(makeTaskCard(task)));
  else todoSection.append(node("p", "muted task-empty", "Rien à traiter pour le moment."));
  host.append(todoSection);

  const doneSection = node("details", "section-card task-fold");
  doneSection.append(node("summary", "task-fold-summary", `Terminées (${completed.length})`));
  if (completed.length) completed.forEach((task) => doneSection.append(makeTaskCard(task)));
  else doneSection.append(node("p", "muted task-empty", "Aucune tâche terminée pour le moment."));
  host.append(doneSection);

  if (other.length) {
    const otherSection = node("details", "section-card task-fold");
    otherSection.append(node("summary", "task-fold-summary", `Mises de côté (${other.length})`));
    other.forEach((task) => otherSection.append(makeTaskCard(task)));
    host.append(otherSection);
  }
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
    const agentMarks = { planner: "▤", coder: "</>", tester: "⌬", verifier: "✓" };
    const mark = node("span", "agent-orb", agentMarks[agent.role] || "◇");
    mark.setAttribute("aria-hidden", "true");
    identity.append(mark);
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
  renderAgentModelAssignments(snapshot, host);
}

function renderAgentModelAssignments(snapshot, host) {
  const panel = section("Modèles par agent");
  panel.append(node("p", "muted", "Choisis un modèle principal et, si tu le souhaites, des modèles de secours ordonnés. Tous les choix sont enregistrés dans les routes du projet."));
  const available = [...new Map((snapshot.routes || []).map((route) => {
    const id = `${route.provider}:${route.model}`;
    return [id, { id, label: `${route.provider} · ${route.model}` }];
  })).values()];
  if (!available.length) {
    panel.append(node("p", "muted", "Aucun modèle enregistré. Ajoute d’abord un fournisseur et un modèle dans Paramètres → API Keys."));
    host.append(panel);
    return;
  }

  const grid = node("div", "agent-model-grid");
  const roles = [
    ["planner", "Planner", "Analyse et planification"],
    ["coder", "Coder", "Propositions de code"],
    ["tester", "Tester", "Préparation des tests"],
  ];
  roles.forEach(([role, label, description]) => {
    const card = node("article", "agent-model-card");
    card.append(node("strong", "", label), node("p", "muted", description));
    const configured = currentRoutes(snapshot)[role] || [];
    const primary = node("select", "select-control agent-model-select");
    primary.setAttribute("aria-label", `Modèle principal pour ${label}`);
    const none = node("option", "", "Aucun modèle principal");
    none.value = "";
    primary.append(none);
    available.forEach((candidate) => {
      const option = node("option", "", candidate.label);
      option.value = candidate.id;
      primary.append(option);
    });
    primary.value = configured[0] || "";
    const primaryField = node("label", "setting-label", "Modèle principal");
    primaryField.append(primary);
    const removePrimary = node("button", "secondary-button agent-remove-primary", "Retirer le modèle principal");
    removePrimary.type = "button";
    removePrimary.disabled = !primary.value;
    removePrimary.addEventListener("click", async () => {
      if (!primary.value) return;
      removePrimary.disabled = true;
      if (!await removeModelRoute(role, primary.value)) removePrimary.disabled = false;
    });
    card.append(primaryField, removePrimary);

    let fallbacks = configured.slice(1);
    const fallbackList = node("div", "agent-fallback-list");
    const fallbackHeading = node("strong", "agent-fallback-heading", "Modèles de secours · ordre d’essai");
    const addFallback = node("button", "secondary-button agent-add-fallback", "+ Ajouter un secours");
    addFallback.type = "button";

    const persist = async () => {
      const routes = currentRoutes(snapshot);
      routes[role] = primary.value ? [primary.value, ...fallbacks.filter((candidate) => candidate !== primary.value)] : [];
      addFallback.disabled = true;
      await saveModelRoutes(routes);
      addFallback.disabled = false;
    };

    const drawFallbacks = () => {
      fallbackList.replaceChildren();
      if (!fallbacks.length) {
        fallbackList.append(node("p", "muted agent-no-fallback", "Aucun modèle de secours."));
        return;
      }
      fallbacks.forEach((modelId, index) => {
        const row = node("div", "agent-fallback-row");
        const select = node("select", "select-control agent-model-select");
        select.setAttribute("aria-label", `Modèle de secours ${index + 1} pour ${label}`);
        available.filter((candidate) => candidate.id === modelId || (candidate.id !== primary.value && !fallbacks.includes(candidate.id))).forEach((candidate) => {
          const option = node("option", "", candidate.label);
          option.value = candidate.id;
          select.append(option);
        });
        select.value = modelId;
        select.addEventListener("change", async () => {
          fallbacks[index] = select.value;
          await persist();
        });
        const moveUp = node("button", "secondary-button agent-reorder-fallback", "↑");
        moveUp.type = "button";
        moveUp.disabled = index === 0;
        moveUp.setAttribute("aria-label", `Monter le modèle de secours ${index + 1} de ${label}`);
        moveUp.addEventListener("click", async () => {
          [fallbacks[index - 1], fallbacks[index]] = [fallbacks[index], fallbacks[index - 1]];
          drawFallbacks();
          await persist();
        });
        const moveDown = node("button", "secondary-button agent-reorder-fallback", "↓");
        moveDown.type = "button";
        moveDown.disabled = index === fallbacks.length - 1;
        moveDown.setAttribute("aria-label", `Descendre le modèle de secours ${index + 1} de ${label}`);
        moveDown.addEventListener("click", async () => {
          [fallbacks[index], fallbacks[index + 1]] = [fallbacks[index + 1], fallbacks[index]];
          drawFallbacks();
          await persist();
        });
        const remove = node("button", "secondary-button agent-remove-fallback", "Retirer");
        remove.type = "button";
        remove.setAttribute("aria-label", `Retirer le modèle de secours ${index + 1} de ${label}`);
        remove.addEventListener("click", async () => {
          remove.disabled = true;
          if (!await removeModelRoute(role, modelId)) remove.disabled = false;
        });
        row.append(select, moveUp, moveDown, remove);
        fallbackList.append(row);
      });
    };

    primary.addEventListener("change", async () => {
      const previousPrimary = configured[0] || "";
      if (previousPrimary && previousPrimary !== primary.value && !fallbacks.includes(previousPrimary)) fallbacks.unshift(previousPrimary);
      fallbacks = primary.value ? fallbacks.filter((candidate) => candidate !== primary.value) : [];
      removePrimary.disabled = !primary.value;
      drawFallbacks();
      await persist();
    });
    addFallback.addEventListener("click", async () => {
      const next = available.find((candidate) => candidate.id !== primary.value && !fallbacks.includes(candidate.id));
      if (!next) { showNotice("Tous les modèles enregistrés sont déjà affectés à ce rôle.", true); return; }
      fallbacks.push(next.id);
      drawFallbacks();
      await persist();
    });
    card.append(fallbackHeading, fallbackList, addFallback);
    drawFallbacks();
    grid.append(card);
  });
  panel.append(grid);
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
    const line = node("div", "route-row model-route-row");
    line.append(node("strong", "", `${route.role} · ${route.order === 1 ? "principal" : `secours ${route.order - 1}`}`));
    line.append(node("span", "route-state", `${route.provider}:${route.model} · ${stateLabel}`));
    const remove = node("button", "secondary-button", "Retirer"); remove.type = "button";
    remove.addEventListener("click", async () => {
      if (!window.confirm(`Retirer ${route.provider}:${route.model} de la route ${route.role} ?`)) return;
      await removeModelRoute(route.role, `${route.provider}:${route.model}`);
    });
    line.append(remove); models.append(line);
  });
  host.append(models);
  const configure = section("Ajouter un modèle aux agents");
  configure.append(node("p", "muted", "Choisis un fournisseur configuré, saisis l’identifiant exact du modèle et sélectionne son rôle et sa priorité. Le premier candidat est principal; les suivants servent de secours."));
  const form = node("form", "model-route-form");
  const providerLabel = node("label", "setting-label", "Fournisseur");
  const provider = node("select", "select-control"); provider.required = true;
  const providerNames = {
    openai: "OpenAI / ChatGPT", anthropic: "Anthropic / Claude", gemini: "Google Gemini",
    nvidia: "NVIDIA", openrouter: "OpenRouter", mistral: "Mistral", groq: "Groq"
  };
  (snapshot.configured_providers || []).forEach((name) => {
    if (!providerNames[name]) return;
    const option = node("option", "", providerNames[name]); option.value = name; provider.append(option);
  });
  providerLabel.append(provider);
  const modelLabel = node("label", "setting-label", "Identifiant exact du modèle");
  const model = node("input", "api-key-input"); model.required = true; model.maxLength = 160; model.placeholder = "Ex. openai/gpt-oss-20b"; model.autocomplete = "off"; model.spellcheck = false;
  modelLabel.append(model);
  const roleLabel = node("label", "setting-label", "Agent");
  const role = node("select", "select-control");
  [["planner", "Planner"], ["coder", "Coder"], ["tester", "Tester"]].forEach(([value, label]) => { const option = node("option", "", label); option.value = value; role.append(option); });
  roleLabel.append(role);
  const priorityLabel = node("label", "setting-label", "Priorité");
  const priority = node("select", "select-control");
  [["primary", "Modèle principal"], ["fallback", "Modèle de secours"]].forEach(([value, label]) => { const option = node("option", "", label); option.value = value; priority.append(option); });
  priorityLabel.append(priority);
  const save = node("button", "primary-button", "Enregistrer la route"); save.type = "submit";
  form.append(providerLabel, modelLabel, roleLabel, priorityLabel, save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const modelId = model.value.trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}$/.test(modelId)) { showNotice("Identifiant de modèle invalide.", true); return; }
    const routes = currentRoutes(snapshot);
    const candidate = `${provider.value}:${modelId}`;
    routes[role.value] = routes[role.value].filter((item) => item !== candidate);
    if (priority.value === "primary") routes[role.value].unshift(candidate);
    else routes[role.value].push(candidate);
    if (routes[role.value].length > 5) { showNotice("Une route peut contenir au maximum cinq modèles.", true); return; }
    save.disabled = true;
    await saveModelRoutes(routes);
    save.disabled = false;
  });
  configure.append(form);
  host.append(configure);
  host.append(noteCard("Disponibilité des modèles", "La route est enregistrée dans vybelix.toml, mais l’accès du compte n’est pas testé ici. Ajoute la clé du fournisseur dans Paramètres → API Keys. Les appels réels restent déclenchés par les agents."));
}

function currentRoutes(snapshot) {
  const routes = { planner: [], coder: [], tester: [] };
  (snapshot.routes || []).forEach((route) => {
    if (routes[route.role]) routes[route.role].push(`${route.provider}:${route.model}`);
  });
  return routes;
}

async function saveModelRoutes(routes) {
  const result = await postAction("/api/models", { routes });
  if (result) { showNotice("Routes de modèles enregistrées dans vybelix.toml."); await refreshSnapshot(); }
}

async function removeModelRoute(role, model) {
  const result = await postAction("/api/models/remove", { role, model });
  if (result) {
    showNotice(`${model} retiré de la route ${role}; les modèles suivants ont été conservés.`);
    await refreshSnapshot();
    return true;
  }
  return false;
}

async function renderSkills(host) {
  host.replaceChildren();
  const panel = section("Skill Builder · gestion locale");
  panel.append(node("p", "muted", "Les skills restent inertes. Aucune capacité n’est exécutée dans cette version."));
  const create = node("form", "skill-create-form");
  create.append(node("h3", "", "Créer un brouillon"));
  const fields = node("div", "skill-create-fields");
  const id = node("input", "file-search"); id.name = "id"; id.required = true; id.pattern = "[a-z0-9]+(?:-[a-z0-9]+)*"; id.maxLength = 64; id.placeholder = "mon-skill"; id.setAttribute("aria-label", "Identifiant du skill");
  const name = node("input", "file-search"); name.name = "name"; name.required = true; name.placeholder = "Nom du skill"; name.setAttribute("aria-label", "Nom du skill");
  const description = node("input", "file-search"); description.name = "description"; description.required = true; description.placeholder = "À quoi sert-il ?"; description.setAttribute("aria-label", "Description du skill");
  const author = node("input", "file-search"); author.name = "author"; author.placeholder = "Auteur (facultatif)"; author.setAttribute("aria-label", "Auteur du skill");
  fields.append(id, name, description, author);
  const createButton = node("button", "primary-action", "Créer le brouillon"); createButton.type = "submit";
  create.append(fields, createButton);
  create.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(create));
    try { await postSkillAction("/api/skills/create", payload); renderSkills(host); }
    catch (error) { showNotice(error.message || "Création impossible.", true); }
  });
  panel.append(create);
  const status = node("p", "muted", "Chargement des skills du projet…");
  panel.append(status);
  host.append(panel);
  try {
    const response = await fetch("/api/skills", { headers: { Accept: "application/json" }, cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Registre local indisponible.");
    status.remove();
    const sandboxNote = data.sandbox || {};
    panel.append(noteCard("Exécution isolée", sandboxNote.detail || "Exécution désactivée."));
    const installed = section(`Installés (${data.installed.length})`);
    if (!data.installed.length) installed.append(node("p", "muted", "Aucun skill installé."));
    data.installed.forEach((skill) => {
      const card = node("article", "skill-card");
      const head = node("div", "skill-card-head");
      const title = node("div", "");
      title.append(node("h3", "", skill.name || skill.id), node("p", "muted", `${skill.id} · v${skill.version} · ${skill.status}`));
      head.append(title, node("span", `skill-status ${skill.status === "enabled" ? "is-enabled" : ""}`, skill.status === "enabled" ? "Activé · inerte" : skill.status === "tampered" ? "Intégrité invalide" : skill.status === "missing" ? "Fichiers absents" : "Désactivé"));
      card.append(head, node("p", "", skill.description || "Aucune description."));
      const perms = node("div", "skill-permissions");
      perms.append(node("strong", "", "Permissions demandées"));
      perms.append(node("span", "", skill.permissions?.length ? skill.permissions.join(" · ") : "Aucune"));
      card.append(perms);
      const actions = node("div", "skill-actions");
      if (["enabled", "disabled"].includes(skill.status)) {
        const dependencies = node("button", "secondary-action", "Dépendances"); dependencies.type = "button";
        dependencies.addEventListener("click", async () => { try { const result=await postSkillAction("/api/skills/dependencies",{id:skill.id}); const details=result.dependencies.map((item)=>`${item.name}: ${item.status}${item.installed_version ? ` · ${item.installed_version}` : ""}`).join("\n") || "Aucune dépendance déclarée."; window.alert(details); } catch(error) { showNotice(error.message || "Diagnostic indisponible.",true); } });
        actions.append(dependencies);
        const runChecks = node("button", "secondary-action", "Tests statiques"); runChecks.type = "button";
        runChecks.addEventListener("click", async () => {
          try { const result = await postSkillAction("/api/skills/test", { id: skill.id }); showNotice(result.passed ? "Contrôles statiques réussis. Les tests d’exécution restent inactifs sans sandbox." : "Contrôles statiques en échec; consulte la vérification.", !result.passed); }
          catch (error) { showNotice(error.message || "Test impossible.", true); }
        });
        actions.append(runChecks);
        const configure = node("button", "secondary-action", "Configurer"); configure.type = "button";
        configure.addEventListener("click", () => configureSkillDialog(skill.id)); actions.append(configure);
      }
      if (skill.status === "enabled") {
        for (const role of ["planner", "coder", "tester"]) {
          const preview = node("button", "secondary-action", `Prévisualiser · ${role}`); preview.type = "button";
          preview.addEventListener("click", async () => {
            try { const context = await postSkillAction("/api/skills/context", { ids: [skill.id], role }); window.alert(`UNTRUSTED_SKILL_DATA · ${role}\n\n${context.skills[0]?.content || "(aucune instruction)"}`); }
            catch (error) { showNotice(error.message || "Aperçu impossible.", true); }
          }); actions.append(preview);
        }
      }
      if (skill.status === "disabled") {
        const enable = node("button", "secondary-action", "Examiner et activer"); enable.type = "button";
        enable.addEventListener("click", async () => {
          const permissions = skill.permissions || [];
          const prompt = `Confirmer les permissions suivantes : ${permissions.length ? permissions.join(", ") : "aucune"}.\n\nLe code du skill ne sera pas exécuté. Continuer ?`;
          if (!window.confirm(prompt)) return;
          try { await postSkillAction("/api/skills/enable", { id: skill.id, permissions }); renderSkills(host); }
          catch (error) { showNotice(error.message || "Activation impossible.", true); }
        });
        actions.append(enable);
      } else if (skill.status === "enabled") {
        const disable = node("button", "secondary-action", "Désactiver"); disable.type = "button";
        disable.addEventListener("click", async () => { try { await postSkillAction("/api/skills/disable", { id: skill.id }); renderSkills(host); } catch (error) { showNotice(error.message || "Désactivation impossible.", true); } });
        actions.append(disable);
      }
      if (["disabled", "enabled", "tampered", "missing"].includes(skill.status)) {
        const remove = node("button", "secondary-action", "Désinstaller"); remove.type = "button";
        remove.addEventListener("click", async () => {
          if (!window.confirm(`Désinstaller ${skill.id} et supprimer sa copie locale ?`)) return;
          try { await postSkillAction("/api/skills/uninstall", { id: skill.id, approved: true }); renderSkills(host); }
          catch (error) { showNotice(error.message || "Désinstallation impossible.", true); }
        });
        actions.append(remove);
      }
      card.append(actions); installed.append(card);
    });
    host.append(installed);

    const candidates = section(`Skills du projet (${data.candidates.length})`);
    candidates.append(node("p", "muted", "Place un dossier de skill validable dans skills/<id>/ pour le voir ici."));
    if (!data.candidates.length) candidates.append(node("p", "muted", "Aucun brouillon trouvé."));
    data.candidates.forEach((candidate) => {
      const card = node("article", "skill-card");
      const skill = candidate.skill;
      card.append(node("h3", "", skill?.name || candidate.source));
      card.append(node("p", "muted", skill ? `${skill.id} · v${skill.version} · ${skill.description}` : candidate.source));
      const perms = skill?.permissions || [];
      card.append(node("p", "skill-permissions", `Permissions : ${perms.length ? perms.join(" · ") : "aucune"}`));
      if (candidate.errors?.length) {
        const errors = node("ul", "skill-errors");
        candidate.errors.forEach((item) => errors.append(node("li", "", item.message)));
        card.append(errors);
      }
      if (candidate.warnings?.length) {
        const warnings = node("ul", "skill-warnings");
        candidate.warnings.forEach((item) => warnings.append(node("li", "", item.message)));
        card.append(warnings);
      }
      const actions = node("div", "skill-actions");
      if (candidate.valid) {
        const isUpdate = candidate.update_available === true;
        const install = node("button", "primary-action", isUpdate ? "Mettre à jour · désactivé" : "Valider et installer désactivé"); install.type = "button";
        install.addEventListener("click", async () => {
          const prompt = `${isUpdate ? "Mettre à jour" : "Installer"} ${skill.id} v${skill.version} désactivé ?\n\nPermissions déclarées : ${perms.length ? perms.join(", ") : "aucune"}\n\nLe code ne sera pas exécuté.`;
          if (!window.confirm(prompt)) return;
          await postSkillAction(isUpdate ? "/api/skills/update" : "/api/skills/install", { source: candidate.source, approved: true });
          renderSkills(host);
        });
        actions.append(install);
      }
      const recheck = node("button", "secondary-action", "Revalider"); recheck.type = "button";
      recheck.addEventListener("click", async () => {
        try { await postSkillAction("/api/skills/validate", { source: candidate.source }); renderSkills(host); }
        catch (error) { showNotice(error.message || "Validation impossible.", true); }
      });
      actions.append(recheck); card.append(actions); candidates.append(card);
    });
    host.append(candidates);
  } catch (error) {
    status.className = "error-text"; status.textContent = error.message || "Impossible de charger les skills.";
  }
}

async function configureSkillDialog(skillId) {
  const response = await fetch("/api/skills/schema", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: skillId }) });
  const data = await response.json();
  if (!response.ok) { showNotice(data.error || "Schéma indisponible.", true); return; }
  const schema = data.schema;
  if (!schema) { showNotice("Ce skill ne demande aucune configuration."); return; }
  const dialog = document.createElement("dialog"); dialog.className = "skill-config-dialog";
  const form = node("form", "skill-create-form"); form.method = "dialog";
  form.append(node("h3", "", `Configuration · ${skillId}`));
  (schema.required || []).forEach((name) => form.append(node("p", "muted", `${name} est obligatoire`)));
  for (const [name, field] of Object.entries(schema.properties || {})) {
    const label = node("label", "setting-label", `${name}${(schema.required || []).includes(name) || field.required ? " *" : ""}`);
    const input = node("input", "api-key-input"); input.name = name; input.required = (schema.required || []).includes(name) || field.required === true;
    input.type = field.type === "secret" || field["x-secret"] === true ? "password" : field.type === "integer" || field.type === "number" ? "number" : field.type === "boolean" ? "checkbox" : "text";
    input.autocomplete = "new-password"; input.spellcheck = false;
    if (field.enum) { const select = node("select", "select-control"); select.name=name; select.required=input.required; field.enum.forEach((value) => { const option=node("option","",String(value)); option.value=String(value); select.append(option); }); label.append(select); }
    else label.append(input);
    form.append(label);
  }
  const actions=node("div","skill-actions"); const save=node("button","primary-action","Enregistrer"); save.type="submit"; const cancel=node("button","secondary-action","Annuler"); cancel.type="button"; cancel.addEventListener("click",()=>dialog.close()); actions.append(cancel,save); form.append(actions); dialog.append(form); document.body.append(dialog);
  form.addEventListener("submit",async(event)=>{event.preventDefault();const values={};for(const [name,field] of Object.entries(schema.properties||{})){const control=form.elements.namedItem(name);if(!control)continue;const required=(schema.required||[]).includes(name)||field.required===true;if(control.type==="checkbox"){if(!control.checked&&!required)continue;values[name]=control.checked;continue;}if(control.value==="")continue;let value=control.type==="number"?(field.type==="integer"?Number.parseInt(control.value,10):Number(control.value)):control.value;if(control.tagName==="SELECT"&&field.type!=="string")value=JSON.parse(control.value);values[name]=value;}try{await postSkillAction("/api/skills/configure",{id:skillId,values});dialog.close();}catch(error){showNotice(error.message||"Configuration refusée.",true);}});
  dialog.addEventListener("close",()=>dialog.remove()); dialog.showModal();
}

async function postSkillAction(url, payload) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(payload) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Action Skill impossible.");
  showNotice("Action Skill terminée.");
  return data;
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

function renderTerminal(snapshot, host) {
  const consolePanel = section("Console · opérations locales");
  consolePanel.append(node("p", "muted", "Suivi des opérations lancées depuis Vybelix. Les commandes libres ne sont pas exécutées par cette interface."));
  const operations = snapshot.operations || [];
  if (!operations.length) consolePanel.append(node("p", "muted", "Aucune opération lancée pendant cette session."));
  const kinds = { plan: "Préparation de plan", code: "Génération de proposition", verify: "Vérification" };
  const statuses = { queued: "En attente", running: "En cours", done: "Terminée", failed: "Échec" };
  operations.forEach((operation) => {
    const detail = [operation.task_id, operation.created_at].filter(Boolean).join(" · ");
    consolePanel.append(row(`${kinds[operation.kind] || operation.kind} · ${statuses[operation.status] || operation.status}`, detail || operation.id));
  });
  host.append(consolePanel);

  const guidance = section("Exécuter une vérification");
  guidance.append(node("p", "muted", "Les commandes contrôlées et leurs résultats sont séparés dans l’espace Vérification."));
  const openVerification = node("button", "secondary-action", "Ouvrir Vérification");
  openVerification.type = "button";
  openVerification.addEventListener("click", () => showView("verification"));
  guidance.append(openVerification);
  host.append(guidance);
}

function renderGit(snapshot, host) {
  const git = section("Dépôt Git · consultation seule");
  git.append(row("Branche", snapshot.git_details.branch || (snapshot.git_details.available ? "détachée" : "Git indisponible")));
  git.append(row("Workspace", snapshot.git_details.available ? (snapshot.git_details.dirty ? "Modifications présentes" : "Propre") : "Non disponible"));
  host.append(git);
  const commits = section("Commits récents");
  if (!snapshot.git_details.commits.length) commits.append(node("p", "muted", "Aucun commit disponible dans le dépôt."));
  snapshot.git_details.commits.forEach((commit) => commits.append(row(`${commit.hash} · ${commit.date}`, commit.subject)));
  host.append(commits);
}

function renderHistory(snapshot, host) {
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

function openApiKeyManager() {
  const dialog = node("dialog", "api-key-dialog");
  const shell = node("section", "api-key-modal-shell");
  const header = node("header", "api-key-modal-header");
  const heading = node("div", "");
  const modalTitle = node("h2", "", "API Keys"); modalTitle.id = "api-key-modal-title";
  heading.append(modalTitle, node("p", "muted", "Gère les clés API utilisées par tes fournisseurs."));
  dialog.setAttribute("aria-labelledby", modalTitle.id);
  const close = node("button", "api-key-close", "×"); close.type = "button"; close.setAttribute("aria-label", "Fermer la fenêtre");
  close.addEventListener("click", () => dialog.close());
  header.append(heading, close);
  const body = node("div", "api-key-modal-body");
  shell.append(header, body); dialog.append(shell); document.body.append(dialog);
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener("close", () => { state.apiKeySession = null; });
  dialog.showModal();
  fetch("/api/keys", { headers: { Accept: "application/json" }, cache: "no-store" })
    .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.error || "Gestionnaire de clés indisponible."); return data; })
    .then((data) => { state.apiKeySetupRequired = Boolean(data.setup_required); renderApiPinForm(body, state.apiKeySetupRequired ? "setup" : "unlock"); })
    .catch((error) => { body.replaceChildren(node("p", "muted", error.message || "Gestionnaire de clés indisponible.")); });
}

function renderApiPinForm(host, mode) {
  host.replaceChildren();
  const setup = mode === "setup";
  const form = node("form", "api-pin-form");
  form.append(node("p", "muted", setup
    ? "Crée un PIN à 6 chiffres. Il protège l’accès aux clés enregistrées localement."
    : "Saisis ton PIN pour déverrouiller les clés API."));
  const pinLabel = node("label", "setting-label", setup ? "Nouveau PIN" : "Code PIN");
  const pin = node("input", "api-key-input");
  pin.type = "password"; pin.inputMode = "numeric"; pin.pattern = "[0-9]{6}"; pin.maxLength = 6; pin.required = true;
  pin.autocomplete = setup ? "new-password" : "current-password"; pin.placeholder = "••••••"; pin.setAttribute("aria-label", "PIN à 6 chiffres");
  pinLabel.append(pin); form.append(pinLabel);
  let confirmation;
  if (setup) {
    const confirmLabel = node("label", "setting-label", "Confirmer le PIN");
    confirmation = node("input", "api-key-input");
    confirmation.type = "password"; confirmation.inputMode = "numeric"; confirmation.pattern = "[0-9]{6}"; confirmation.maxLength = 6; confirmation.required = true; confirmation.autocomplete = "new-password"; confirmation.placeholder = "••••••"; confirmation.setAttribute("aria-label", "Confirmer le PIN à 6 chiffres");
    confirmLabel.append(confirmation); form.append(confirmLabel);
  }
  form.append(node("p", "muted", "Les valeurs restent masquées dans l’interface et ne sont jamais renvoyées par le serveur."));
  const submit = node("button", "primary-button", setup ? "Créer le PIN" : "Déverrouiller"); submit.type = "submit"; form.append(submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!/^\d{6}$/.test(pin.value) || (setup && confirmation.value !== pin.value)) {
      showNotice(setup ? "Saisis le même PIN de 6 chiffres dans les deux champs." : "Le PIN doit contenir exactement 6 chiffres.", true); return;
    }
    submit.disabled = true;
    const result = await apiKeyRequest("/api/keys/pin", { action: setup ? "setup" : "unlock", pin: pin.value, confirmation: confirmation?.value });
    pin.value = ""; if (confirmation) confirmation.value = "";
    if (result?.session_token) {
      state.apiKeySession = result.session_token;
      const keys = await apiKeyRequest("/api/keys", null, "GET");
      if (keys) renderApiKeyProviders(host, keys.keys || []);
      else { state.apiKeySession = null; submit.disabled = false; }
    } else submit.disabled = false;
  });
  host.append(form);
  pin.focus();
}

function renderApiKeyProviders(host, entries = []) {
  host.replaceChildren();
  const tabs = node("div", "api-key-tabs");
  const content = node("div", "api-key-tab-content");
  const drawTab = (active) => {
    tabs.replaceChildren();
    const providersTab = node("button", `api-key-tab ${active === "providers" ? "active" : ""}`, "Fournisseurs & modèles");
    providersTab.type = "button";
    providersTab.setAttribute("aria-pressed", String(active === "providers"));
    providersTab.addEventListener("click", () => drawTab("providers"));
    const securityTab = node("button", `api-key-tab ${active === "security" ? "active" : ""}`, "Sécurité & accès");
    securityTab.type = "button";
    securityTab.setAttribute("aria-pressed", String(active === "security"));
    securityTab.addEventListener("click", () => drawTab("security"));
    tabs.append(providersTab, securityTab);
    content.replaceChildren();
    if (active === "security") {
      const security = section("Sécurité des clés API");
      security.append(node("p", "muted", "L’accès au gestionnaire est protégé par un PIN local. Les clés sont enregistrées dans le fichier .env du projet, ignoré par Git, puis chargées par Vybelix pour ses appels fournisseurs."));
      security.append(node("p", "muted", "Le fichier .env est en clair sur le disque : le PIN protège l’accès à l’interface, mais ne chiffre pas les clés. Ne partage pas ce fichier et protège ton compte Windows."));
      security.append(row("Affichage des clés", "Valeurs jamais renvoyées ni affichées"));
      security.append(row("Durée de session déverrouillée", "15 minutes sans activité"));
      content.append(security);
    } else drawProviders(content, entries);
  };
  host.append(tabs, content);
  drawTab("providers");
}

function drawProviders(host, entries) {
  const intro = node("p", "muted", "Choisis un fournisseur, renseigne un identifiant de modèle et ajoute sa clé API. Les clés sont stockées localement dans .env; les routes d’agents restent celles configurées dans vybelix.toml.");
  host.append(intro);
  const providerSpecs = [
    { id: "openai", label: "OpenAI / ChatGPT", env: "OPENAI_API_KEY", models: ["gpt-4o", "gpt-4o-mini", "o3-mini"] },
    { id: "anthropic", label: "Anthropic / Claude", env: "ANTHROPIC_API_KEY", models: ["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"] },
    { id: "gemini", label: "Google Gemini", env: "GEMINI_API_KEY", models: ["gemini-3.7-flash"] },
    { id: "groq", label: "Groq", env: "Groq_API_KEY", models: ["moonshotai/kimi-k2-instruct"] },
    { id: "mistral", label: "Mistral AI", env: "Mistral_API_KEY", models: ["mistral-medium-3.5-128b"] },
    { id: "openrouter", label: "OpenRouter", env: "Openrouter_API_KEY", models: ["openai/gpt-oss-20b", "anthropic/claude-sonnet-4", "google/gemini-2.5-flash"] },
    { id: "nvidia", label: "NVIDIA", env: "Nvidia_API_KEY", models: ["z-ai/glm-5.2"] },
  ];
  const grid = node("div", "api-provider-grid");
  providerSpecs.forEach((provider) => {
    const entry = entries.find((item) => item.name === provider.env);
    const activeRoutes = (state.snapshot?.routes || []).filter((route) => route.provider === provider.id);
    const card = node("article", "api-key-card");
    const heading = node("div", "api-key-heading");
    heading.append(node("strong", "", provider.label), node("span", `api-key-state ${entry?.configured ? "configured" : ""}`, entry?.configured ? "Clé enregistrée" : "Clé absente"));
    heading.append(node("small", "muted", `Modèles suggérés : ${provider.models.slice(0, 2).join(" · ")}`));
    if (activeRoutes.length) heading.append(node("small", "api-model-current", `Routes actives · ${activeRoutes.map((route) => `${route.role}: ${route.model}`).join(" · ")}`));
    const actions = node("div", "api-key-actions");
    const edit = node("button", "secondary-button", entry?.configured ? "Configurer le modèle" : "Ajouter une clé et un modèle"); edit.type = "button";
    edit.addEventListener("click", () => renderApiKeyForm(host, provider.env, entries, provider));
    actions.append(edit);
    if (entry?.configured) {
    const remove = node("button", "secondary-button", "Retirer"); remove.type = "button";
      remove.addEventListener("click", async () => { if (await apiKeyRequest("/api/keys", { name: provider.env, key: "" })) refreshApiKeyList(host); });
      actions.append(remove);
    }
    card.append(heading, actions); grid.append(card);
  });
  host.append(grid);
  const other = entries.filter((entry) => !providerSpecs.some((provider) => provider.env === entry.name));
  if (other.length) {
    const extra = section("Autres clés enregistrées");
    other.forEach((entry) => {
      const line = node("div", "route-row");
      line.append(node("strong", "", entry.name), node("span", "route-state", entry.configured ? "Configurée · masquée" : "Absente"));
      const remove = node("button", "secondary-button", "Retirer"); remove.type = "button";
      remove.addEventListener("click", async () => { if (await apiKeyRequest("/api/keys", { name: entry.name, key: "" })) refreshApiKeyList(host); });
      line.append(remove); extra.append(line);
    });
    host.append(extra);
  }
}

function renderApiKeyForm(host, existingName = null, entries = [], provider = null) {
  const previous = host.querySelector(".api-key-form"); if (previous) previous.remove();
  const form = node("form", "api-key-form api-model-form");
  form.append(node("h3", "", provider ? `Ajouter ${provider.label}` : existingName ? "Remplacer une clé API" : "Ajouter une clé API"));
  const name = node("input", "api-key-input"); name.type = "text"; name.required = true; name.maxLength = 64; name.pattern = "[A-Za-z_][A-Za-z0-9_]{0,63}"; name.placeholder = "GEMINI_API_KEY"; name.autocomplete = "off"; name.spellcheck = false; name.setAttribute("aria-label", "Nom de la variable API");
  name.value = provider?.env || existingName || "";
  if (existingName) name.readOnly = true;
  const modelLabel = node("label", "setting-label", "Identifiant du modèle");
  const model = node("input", "api-key-input"); model.type = "text"; model.required = true; model.maxLength = 160; model.placeholder = "Ex. gpt-4o-mini"; model.autocomplete = "off"; model.spellcheck = false;
  if (provider?.models) {
    const suggestions = node("div", "api-model-suggestions");
    provider.models.forEach((id) => { const choice = node("button", "api-model-chip", id); choice.type = "button"; choice.addEventListener("click", () => { model.value = id; }); suggestions.append(choice); });
    form.append(suggestions);
  }
  modelLabel.append(model);
  const roleLabel = node("label", "setting-label", "Agent à configurer");
  const role = node("select", "select-control");
  [["planner", "Planner"], ["coder", "Coder"], ["tester", "Tester"]].forEach(([value, label]) => { const option = node("option", "", label); option.value = value; role.append(option); });
  roleLabel.append(role);
  const priorityLabel = node("label", "setting-label", "Priorité du modèle");
  const priority = node("select", "select-control");
  [["primary", "Principal"], ["fallback", "Secours"]].forEach(([value, label]) => { const option = node("option", "", label); option.value = value; priority.append(option); });
  priorityLabel.append(priority);
  const keyLabel = node("label", "setting-label", "Clé API");
  const key = node("input", "api-key-input"); key.type = "password"; key.required = true; key.maxLength = 4096; key.autocomplete = "new-password"; key.spellcheck = false; key.placeholder = existingName ? "Clé de remplacement" : "Coller la clé API"; key.setAttribute("aria-label", "Valeur de la clé API");
  keyLabel.append(key);
  form.append(node("label", "setting-label", "Nom de variable pour la clé"), name, modelLabel);
  if (provider) form.append(roleLabel, priorityLabel);
  form.append(keyLabel, node("p", "muted", provider ? "À l’enregistrement, la clé sera stockée localement et ce modèle sera ajouté à la route de l’agent choisi dans vybelix.toml." : "La clé sera stockée localement dans le .env du projet."));
  const actions = node("div", "api-key-actions");
  const save = node("button", "primary-button", existingName ? "Enregistrer la clé" : "Ajouter au coffre"); save.type = "submit";
  const testStatus = node("p", "api-key-test-status muted", "Le test envoie une courte requête au fournisseur et peut être facturé.");
  testStatus.setAttribute("aria-live", "polite");
  let test = null;
  if (provider) {
    test = node("button", "secondary-button api-key-test", "Tester"); test.type = "button";
    test.setAttribute("aria-label", `Tester l’appel ${provider.label}`);
    test.addEventListener("click", async () => {
      if (!model.value.trim() || !key.value) { testStatus.textContent = "Renseigne le modèle et la clé API pour lancer le test."; testStatus.dataset.state = "error"; return; }
      test.disabled = true; testStatus.textContent = "Test de l’appel en cours…"; testStatus.dataset.state = "pending";
      const result = await apiKeyRequest("/api/keys/test", { provider: provider.id, model: model.value.trim(), key: key.value }, "POST", { quiet: true });
      test.disabled = false;
      if (result?.ok) { testStatus.textContent = `Connexion réussie · ${result.provider} · ${result.model} · ${result.latencyMs} ms`; testStatus.dataset.state = "success"; }
      else { testStatus.textContent = `Échec du test · ${result?.error || "Erreur réseau ou réponse invalide."}`; testStatus.dataset.state = "error"; }
    });
  }
  const cancel = node("button", "secondary-button", "Annuler"); cancel.type = "button"; cancel.addEventListener("click", () => renderApiKeyProviders(host, entries));
  cancel.classList.add("api-key-cancel");
  actions.append(save);
  if (test) actions.append(test);
  actions.append(cancel); form.append(actions);
  if (test) form.append(testStatus);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!name.checkValidity() || !key.value) { showNotice("Renseigne le nom et la clé API.", true); return; }
    save.disabled = true;
    const result = await apiKeyRequest("/api/keys", { name: name.value.trim(), key: key.value });
    key.value = "";
    if (result) {
      if (provider && model.value.trim()) {
        const routes = currentRoutes(state.snapshot || {});
        const candidate = `${provider.id}:${model.value.trim()}`;
        routes[role.value] = routes[role.value].filter((item) => item !== candidate);
        if (priority.value === "primary") routes[role.value].unshift(candidate);
        else routes[role.value].push(candidate);
        if (routes[role.value].length > 5) {
          showNotice("Clé enregistrée, mais l’ajout de route dépasserait la limite de cinq candidats.", true);
          refreshApiKeyList(host);
          return;
        }
        const routeResult = await postAction("/api/models", { routes });
        if (routeResult) {
          showNotice("Clé enregistrée et modèle ajouté à la route de l’agent.");
          await refreshSnapshot();
        } else {
          showNotice("Clé enregistrée, mais la route du modèle n’a pas pu être mise à jour.", true);
        }
      }
      refreshApiKeyList(host);
    } else save.disabled = false;
  });
  host.append(form);
  name.focus();
}

async function apiKeyRequest(path, payload = null, method = "POST", { quiet = false } = {}) {
  try {
    const headers = { Accept: "application/json" };
    if (state.apiKeySession) headers.Authorization = `Bearer ${state.apiKeySession}`;
    const options = { method, headers, cache: "no-store" };
    if (payload !== null) { headers["Content-Type"] = "application/json"; options.body = JSON.stringify(payload); }
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Erreur HTTP ${response.status}`);
    return data;
  } catch (error) {
    const message = error.message || "Action sur les clés impossible.";
    if (quiet) return { error: message };
    showNotice(message, true); return null;
  }
}

async function refreshApiKeyList(host) {
  const result = await apiKeyRequest("/api/keys", null, "GET");
  if (result) renderApiKeyProviders(host, result.keys || []);
}

const userLevels = [
  ["beginner", "Débutant", "Des explications simples, des étapes guidées et un résumé clair."],
  ["intermediate", "Intermédiaire", "Un bon équilibre entre explications et détails techniques."],
  ["pro", "Expert", "Des résultats concis, précis et orientés détails techniques."]
];

async function saveUserLevel(level, button, status) {
  const label = userLevels.find(([id]) => id === level)?.[1] || level;
  button.disabled = true;
  button.textContent = "Enregistrement…";
  status.textContent = "";
  try {
    const response = await fetch("/api/user-level", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ level }),
      cache: "no-store"
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 404 || response.status === 405) {
        throw new Error("Le serveur Vybelix doit être redémarré pour charger l’enregistrement du niveau. Relance Vybelix, puis actualise cette page.");
      }
      throw new Error(data.error || "Erreur HTTP " + response.status);
    }
    state.onboardingSelection = null;
    await refreshSnapshot();
    if (!state.snapshot?.user_level_selected) {
      throw new Error("Le niveau a peut-être été enregistré, mais l’état ne s’est pas actualisé. Recharge la page.");
    }
    showNotice("Niveau " + label + " enregistré.");
  } catch (error) {
    status.textContent = error.message || "Impossible d’enregistrer le niveau. Relance Vybelix et réessaie.";
    button.disabled = false;
    button.textContent = button.dataset.label;
  }
}

function renderLevelSelector(host, snapshot, onboarding = false) {
  const selectedLevel = onboarding ? (state.onboardingSelection || "") : (snapshot.user_level || "beginner");
  const choices = node("div", "level-choice-grid");
  let draft = selectedLevel;
  const buttons = [];
  for (const [id, label, description] of userLevels) {
    const button = node("button", "level-choice");
    button.type = "button";
    button.setAttribute("aria-pressed", String(draft === id));
    button.append(node("strong", "", label), node("span", "", description));
    button.addEventListener("click", () => {
      draft = id;
      if (onboarding) state.onboardingSelection = id;
      for (const [choice, option] of buttons) option.setAttribute("aria-pressed", String(choice === id));
      save.disabled = !draft;
    });
    buttons.push([id, button]);
    choices.append(button);
  }
  const saveLabel = onboarding ? "Continuer" : "Enregistrer le niveau";
  const save = node("button", "primary-button level-save", saveLabel);
  save.type = "button";
  save.dataset.label = saveLabel;
  save.disabled = !draft;
  const status = node("p", "level-save-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  save.addEventListener("click", () => { if (draft) saveUserLevel(draft, save, status); });
  host.append(choices, save, status);
}

function renderLevelOnboarding(snapshot) {
  const overlay = byId("level-onboarding");
  if (!overlay) return;
  const pending = !snapshot.user_level_selected;
  overlay.hidden = !pending;
  const shell = document.querySelector(".app-shell");
  if (shell) Array.from(shell.children).forEach((child) => { if (child !== overlay) child.inert = pending; });
  if (pending) {
    const host = byId("level-choice-content");
    host.replaceChildren();
    renderLevelSelector(host, snapshot, true);
    host.querySelector("button")?.focus({ preventScroll: true });
  } else {
    state.onboardingSelection = null;
  }
}

function renderSettings(snapshot, host) {
  const level = section("Niveau d’accompagnement");
  level.classList.add("level-preference");
  level.append(node("p", "muted", "Adapte la clarté et le niveau de détail des réponses de Vybelix. Ce réglage ne change ni les contrôles ni les permissions."));
  renderLevelSelector(level, snapshot);
  host.append(level);
  const safe = section("Configuration active · lecture seule");
  safe.append(row("Projet", snapshot.project.name));
  safe.append(row("Routes", `${snapshot.routes.length} candidat(s) configuré(s)`));
  safe.append(row("Timeout modèle", `${snapshot.runtime.request_timeout_seconds ?? "non défini"} s`));
  safe.append(row("Taille maximale de fichier", `${snapshot.runtime.max_file_bytes ?? "non définie"} octets`));
  safe.append(row("Corrections maximales", snapshot.runtime.correction_attempts ?? "non définies"));
  safe.append(row("Commandes autorisées", snapshot.allowed_commands.length));
  safe.append(node("p", "muted", "Les routes modèle se modifient dans vybelix.toml après choix explicite."));
  const apiKeys = section("API KEYS");
  apiKeys.classList.add("api-key-settings");
  apiKeys.append(node("p", "muted", "Ajoute les clés de tes fournisseurs, choisis un modèle recommandé et teste sa connexion depuis le coffre local."));
  const openKeys = node("button", "primary-button api-key-open", "Gérer les clés API");
  openKeys.type = "button"; openKeys.addEventListener("click", openApiKeyManager);
  apiKeys.append(openKeys); host.append(apiKeys); host.append(safe);
  const context = section("Contexte compact du projet");
  context.classList.add("project-context-settings");
  context.append(node("p", "muted", "Notes locales validées et conservées dans .vybelix-cache. Elles ne sont pas envoyées automatiquement aux modèles."));
  const form = node("form", "settings-form project-context-form");
  const goalLabel = node("label", "setting-label", "Objectif du projet");
  const goal = node("textarea", "text-input"); goal.rows = 3; goal.name = "goal"; goal.maxLength = 4000;
  goalLabel.append(goal); form.append(goalLabel);
  const listFields = [
    ["verified_facts", "Faits vérifiés"], ["assumptions", "Hypothèses"], ["entry_points", "Points d’entrée"],
    ["conventions", "Conventions"], ["decisions", "Décisions"], ["open_issues", "Points ouverts"], ["next_steps", "Prochaines étapes"]
  ];
  const controls = {};
  listFields.forEach(([name, labelText]) => {
    const label = node("label", "setting-label", `${labelText} · une entrée par ligne`);
    const textarea = node("textarea", "text-input"); textarea.rows = 2; textarea.name = name; textarea.maxLength = 12000;
    controls[name] = textarea; label.append(textarea); form.append(label);
  });
  const filesLabel = node("label", "setting-label", "Fichiers pertinents · JSON [ { \"path\": \"src/...\", \"summary\": \"...\" } ]");
  const files = node("textarea", "text-input"); files.rows = 4; files.name = "relevant_files"; files.maxLength = 16000; files.value = "[]";
  filesLabel.append(files); form.append(filesLabel);
  const saveContext = node("button", "primary-button", "Enregistrer le contexte"); saveContext.type = "submit"; form.append(saveContext);
  const contextStatus = node("p", "muted", "Chargement du contexte local…"); contextStatus.setAttribute("role", "status"); form.append(contextStatus);
  fetch("/api/context", { headers: { Accept: "application/json" }, cache: "no-store" }).then(async (response) => {
    const data = await response.json(); if (!response.ok) throw new Error(data.error || "Contexte indisponible");
    goal.value = data.goal || "";
    listFields.forEach(([name]) => { controls[name].value = (data[name] || []).join("\n"); });
    files.value = JSON.stringify(data.relevant_files || [], null, 2);
    contextStatus.textContent = data.updated_at ? `Dernière sauvegarde : ${data.updated_at}` : "Aucun contexte enregistré pour le moment.";
  }).catch((error) => { contextStatus.textContent = error.message; contextStatus.classList.add("error"); });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    let relevantFiles;
    try { relevantFiles = JSON.parse(files.value || "[]"); }
    catch { contextStatus.textContent = "Le champ des fichiers pertinents doit être du JSON valide."; contextStatus.classList.add("error"); return; }
    const payload = { goal: goal.value, relevant_files: relevantFiles };
    listFields.forEach(([name]) => { payload[name] = controls[name].value.split("\n").map((item) => item.trim()).filter(Boolean); });
    const result = await postAction("/api/context", payload);
    if (result) { contextStatus.textContent = `Contexte enregistré localement : ${result.updated_at}`; contextStatus.classList.remove("error"); showNotice("Contexte projet enregistré localement."); }
  });
  context.append(form); host.append(context);
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
  const slot = byId("action-notice-slot");
  if (!slot) return;
  const toast = node("span", "action-notice", message);
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");
  toast.title = message;
  toast.classList.toggle("error", error);
  slot.append(toast);
  slot.scrollLeft = slot.scrollWidth;
  slot.scrollTop = slot.scrollHeight;
  toast.dismissTimer = window.setTimeout(() => toast.remove(), 60_000);
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
  const status = node("p", "operation-status", `${label} · en préparation…`);
  const elapsedLabel = node("span", "operation-elapsed", "0 s");
  status.append(elapsedLabel);
  host.append(status);
  const started = await postAction(path, payload);
  if (!started) { status.remove(); return null; }
  const startedAt = Date.now();
  const elapsedTimer = window.setInterval(() => {
    elapsedLabel.textContent = `${Math.floor((Date.now() - startedAt) / 1000)} s écoulées`;
  }, 1000);
  let operation;
  try {
    for (let elapsed = 0; elapsed < 900000; elapsed += 900) {
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      const response = await fetch(`/api/operations/${encodeURIComponent(started.operation_id)}`, { headers: { Accept: "application/json" }, cache: "no-store" });
      operation = await response.json();
      if (!response.ok) throw new Error(operation.error || "Opération introuvable.");
      status.firstChild.textContent = operation.status === "queued" ? `${label} · en file… ` : operation.status === "running" ? `${label} · traitement… ` : operation.status;
      if (operation.status === "done") break;
      if (operation.status === "failed") throw new Error(operation.error?.message || "L’opération a échoué.");
    }
    if (!operation || operation.status !== "done") throw new Error("Délai d’attente UI dépassé ; vérifie l’état avant de relancer.");
    state.lastRouting = operation.result?.routing || [];
    window.clearInterval(elapsedTimer);
    status.remove();
    await refreshSnapshot();
    return operation.result;
  } catch (error) {
    window.clearInterval(elapsedTimer);
    status.remove();
    showNotice(error.message || "Opération échouée.", true);
    await refreshSnapshot();
    return null;
  }
}

function renderConnectedView(view, snapshot) {
  const host = byId("view-content");
  const previousInput = view === "chat" ? host.querySelector(".chat-input") : null;
  const restoreInputFocus = previousInput && document.activeElement === previousInput;
  const selection = restoreInputFocus ? { start: previousInput.selectionStart, end: previousInput.selectionEnd, direction: previousInput.selectionDirection } : null;
  if (previousInput) state.chatDraft = previousInput.value;
  const [title, subtitle] = titles[view] || titles.dashboard;
  byId("view-title").textContent = title;
  byId("view-subtitle").textContent = subtitle;
  host.replaceChildren();
  if (view === "dashboard") renderDashboard(snapshot, host);
  else if (view === "chat") renderChat(snapshot, host);
  else if (view === "tasks") renderTasks(snapshot, host);
  else if (view === "agents") renderAgents(snapshot, host);
  else if (view === "models") renderModels(snapshot, host);
  else if (view === "skills") renderSkills(host);
  else if (view === "files") renderFiles(snapshot, host);
  else if (view === "changes") renderChanges(snapshot, host);
  else if (view === "terminal") renderTerminal(snapshot, host);
  else if (view === "verification") renderVerification(snapshot, host);
  else if (view === "git") renderGit(snapshot, host);
  else if (view === "history") renderHistory(snapshot, host);
  else if (view === "settings") renderSettings(snapshot, host);
  else renderDashboard(snapshot, host);
  if (restoreInputFocus) {
    const input = host.querySelector(".chat-input");
    input?.focus({ preventScroll: true });
    if (input && selection) input.setSelectionRange(selection.start, selection.end, selection.direction);
  }
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
  renderLevelOnboarding(snapshot);
  if (snapshot.user_level_selected && !localStorage.getItem(tourStorageKey)) window.setTimeout(() => {
    if (state.tourIndex === null && !localStorage.getItem(tourStorageKey)) startProductTour();
  }, 650);
}

function showView(view) {
  if (state.snapshot && !state.snapshot.user_level_selected) {
    renderLevelOnboarding(state.snapshot);
    return;
  }
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
byId("open-tour").addEventListener("click", startProductTour);

function startProductTour() {
  state.tourIndex = 0;
  renderProductTourStep();
}

function renderProductTourStep() {
  if (state.tourKeyHandler) document.removeEventListener("keydown", state.tourKeyHandler);
  if (state.tourResizeHandler) window.removeEventListener("resize", state.tourResizeHandler);
  document.getElementById("product-tour")?.remove();
  if (state.tourIndex === null) return;
  const step = tourSteps[state.tourIndex];
  showView(step.view);
  const target = document.querySelector(step.selector);
  if (!target) { finishProductTour(); return; }

  const overlay = node("div", "product-tour-overlay"); overlay.id = "product-tour";
  overlay.setAttribute("role", "presentation");
  const spotlight = node("div", "tour-spotlight"); spotlight.setAttribute("aria-hidden", "true");
  const card = node("section", "tour-card"); card.id = "tour-card";
  card.setAttribute("role", "dialog"); card.setAttribute("aria-modal", "true"); card.setAttribute("aria-labelledby", "tour-title");
  const counter = node("p", "tour-counter", `${state.tourIndex + 1} sur ${tourSteps.length}`);
  const title = node("h2", "", step.title); title.id = "tour-title";
  const description = node("p", "tour-description", step.text);
  const actions = node("div", "tour-actions");
  const skip = node("button", "tour-skip", "Ignorer"); skip.type = "button"; skip.addEventListener("click", finishProductTour);
  actions.append(skip);
  if (state.tourIndex > 0) {
    const back = node("button", "tour-back", "Retour"); back.type = "button";
    back.addEventListener("click", () => { state.tourIndex -= 1; renderProductTourStep(); });
    actions.append(back);
  }
  const next = node("button", "tour-next", state.tourIndex === tourSteps.length - 1 ? "Terminé" : "Suivant"); next.type = "button";
  next.addEventListener("click", () => {
    if (state.tourIndex === tourSteps.length - 1) { finishProductTour(); return; }
    state.tourIndex += 1; renderProductTourStep();
  });
  actions.append(next); card.append(counter, title, description, actions); overlay.append(spotlight, card); document.body.append(overlay);

  const place = () => {
    if (!overlay.isConnected) return;
    const rect = target.getBoundingClientRect();
    spotlight.style.left = `${Math.max(4, rect.left - 4)}px`;
    spotlight.style.top = `${Math.max(4, rect.top - 4)}px`;
    spotlight.style.width = `${Math.max(0, rect.width + 8)}px`;
    spotlight.style.height = `${Math.max(0, rect.height + 8)}px`;
    if (window.innerWidth <= 620) {
      card.style.left = "16px"; card.style.right = "16px"; card.style.top = "auto"; card.style.bottom = "20px";
    } else {
      card.style.width = "min(360px, calc(100vw - 32px))";
      const cardWidth = card.getBoundingClientRect().width;
      const left = rect.left < window.innerWidth * .46 ? rect.right + 18 : rect.left - cardWidth - 18;
      card.style.left = `${Math.max(16, Math.min(window.innerWidth - cardWidth - 16, left))}px`;
      card.style.right = "auto";
      const cardHeight = card.getBoundingClientRect().height;
      card.style.top = `${Math.max(16, Math.min(window.innerHeight - cardHeight - 16, rect.top + rect.height / 2 - cardHeight / 2))}px`;
      card.style.bottom = "auto";
    }
  };
  requestAnimationFrame(place);
  state.tourResizeHandler = place;
  window.addEventListener("resize", place, { passive: true });
  const onKey = (event) => {
    if (event.key === "Escape") { event.preventDefault(); finishProductTour(); }
    else if (event.key === "ArrowRight" && state.tourIndex < tourSteps.length - 1) { event.preventDefault(); state.tourIndex += 1; renderProductTourStep(); }
    else if (event.key === "ArrowLeft" && state.tourIndex > 0) { event.preventDefault(); state.tourIndex -= 1; renderProductTourStep(); }
  };
  state.tourKeyHandler = onKey;
  document.addEventListener("keydown", onKey);
  next.focus({ preventScroll: true });
}

function finishProductTour() {
  state.tourIndex = null;
  if (state.tourKeyHandler) document.removeEventListener("keydown", state.tourKeyHandler);
  if (state.tourResizeHandler) window.removeEventListener("resize", state.tourResizeHandler);
  state.tourKeyHandler = null; state.tourResizeHandler = null;
  localStorage.setItem(tourStorageKey, "completed");
  document.getElementById("product-tour")?.remove();
  byId("open-tour")?.focus({ preventScroll: true });
}

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
