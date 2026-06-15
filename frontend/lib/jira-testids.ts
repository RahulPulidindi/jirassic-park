/**
 * Canonical `data-testid` constants for Jirassic Park's UI.
 *
 * These mirror Atlassian's well-known testid naming pattern
 * (`issue.views.field.<field>.<sub>`, `issue.actions.<action>`, ...). A DOM-
 * driven agent that learned to query Atlassian Cloud by these testids can
 * query ours by the exact same strings.
 *
 * Where Atlassian uses a generated suffix (e.g. `issue.views.field.summary.
 * read-view.summary-text`) we keep the prefix and the most-stable terminal
 * segment so test selectors remain stable across releases.
 *
 * NEVER use raw string testids in the components — always import from here.
 * That gives one source of truth and lets us snapshot-diff against real
 * Atlassian's testid surface from a single file.
 */

export const TESTID = {
  // ------------------------- Global navigation -----------------------------
  appShell: "ak-global-app-shell",
  topNav: {
    container: "atlassian-navigation",
    appSwitcher: "app-switcher.menu",
    productHome: "product-home.button",
    create: "navigation-apps.action-buttons.create.button",
    search: {
      container: "quick-search.container",
      input: "quick-search.input",
      result: (key: string) => `quick-search.result.${key}`,
      keyShortcut: "quick-search.shortcut-key",
      seeAll: "quick-search.see-all",
    },
    notifications: "notifications.button",
    help: "help.button",
    settings: "settings.button",
    profile: "profile.button",
  },
  sidebar: {
    container: "spa-apps-sidebar",
    item: (key: string) => `spa-apps-sidebar.${key}`,
    projectsHeader: "spa-apps-sidebar.starred-projects",
    project: (projectKey: string) => `spa-apps-sidebar.project.${projectKey}`,
    projectBoard: (projectKey: string) => `spa-apps-sidebar.project.${projectKey}.board`,
    projectBacklog: (projectKey: string) => `spa-apps-sidebar.project.${projectKey}.backlog`,
    projectSettings: (projectKey: string) => `spa-apps-sidebar.project.${projectKey}.settings`,
    filtersHeader: "spa-apps-sidebar.filters",
    filter: (filterId: string) => `spa-apps-sidebar.filter.${filterId}`,
  },

  // ------------------------- Create issue modal ----------------------------
  createModal: {
    container: "issue-create.ui.modal.modal-form-container",
    dialog: "issue-create.ui.modal",
    header: "issue-create.ui.modal.title",
    minimize: "issue-create.ui.modal.minimize",
    expand: "issue-create.ui.modal.expand",
    more: "issue-create.ui.modal.more",
    close: "issue-create.ui.modal.close",
    requiredLegend: "issue-create.ui.modal.required-legend",

    field: {
      project: "issue-create.ui.modal.field.project",
      issueType: "issue-create.ui.modal.field.issuetype",
      status: "issue-create.ui.modal.field.status",
      summary: "issue-create.ui.modal.field.summary",
      summaryInput: "issue-create.ui.modal.field.summary.input",
      summaryError: "issue-create.ui.modal.field.summary.error",
      description: "issue-create.ui.modal.field.description",
      descriptionEditor: "issue-create.ui.modal.field.description.editor",
      assignee: "issue-create.ui.modal.field.assignee",
      assigneeAssignToMe: "issue-create.ui.modal.field.assignee.assign-to-me",
      priority: "issue-create.ui.modal.field.priority",
      parent: "issue-create.ui.modal.field.parent",
      dueDate: "issue-create.ui.modal.field.duedate",
      labels: "issue-create.ui.modal.field.labels",
      team: "issue-create.ui.modal.field.team",
      startDate: "issue-create.ui.modal.field.startdate",
      sprint: "issue-create.ui.modal.field.sprint",
      storyPoints: "issue-create.ui.modal.field.customfield_10016",
      reporter: "issue-create.ui.modal.field.reporter",
      attachment: "issue-create.ui.modal.field.attachment",
      linkedIssues: "issue-create.ui.modal.field.issuelinks",
      linkType: "issue-create.ui.modal.field.issuelinks.link-type",
      linkTarget: "issue-create.ui.modal.field.issuelinks.target",
      restrictTo: "issue-create.ui.modal.field.security",
      flagged: "issue-create.ui.modal.field.customfield_10019",
    },

    createAnother: "issue-create.ui.modal.footer.create-another",
    cancel: "issue-create.ui.modal.footer.cancel",
    submit: "issue-create.ui.modal.footer.create",

    error: "issue-create.ui.modal.error-banner",
  },

  // ------------------------- Issue detail page -----------------------------
  issuePage: {
    container: "issue.views.issue-base",
    breadcrumb: "issue.views.issue-base.foundation.breadcrumbs",
    parentLink: "issue.views.issue-base.foundation.breadcrumbs.parent-issue",
    keyLink: "issue.views.issue-base.foundation.breadcrumbs.current-issue",

    // Top toolbar (right of the title row)
    toolbar: {
      container: "issue.views.issue-base.foundation.status",
      status: "issue.fields.status.common.ui.status-view",
      statusDropdown: "issue.fields.status.common.ui.status-button",
      agents: "issue.views.issue-base.foundation.agents",
      automation: "issue.views.issue-base.foundation.automation",
      improve: "issue.views.issue-base.foundation.improve",
      watch: "issue.views.issue-base.foundation.watch",
      lock: "issue.views.issue-base.foundation.lock",
      share: "issue.views.issue-base.foundation.share",
      more: "issue.views.issue-base.foundation.more",
      minimize: "issue.views.issue-base.foundation.minimize",
      close: "issue.views.issue-base.foundation.close",
    },

    // Title
    title: {
      container: "issue.views.issue-base.foundation.summary",
      heading: "issue.views.issue-base.foundation.summary.heading",
      editButton: "issue.views.issue-base.foundation.summary.edit-button",
      addBelow: "issue.views.issue-base.foundation.summary.add-below",
      titleMore: "issue.views.issue-base.foundation.summary.more",
    },

    // Body sections
    description: {
      container: "issue.views.field.rich-text.description",
      readView: "issue.views.field.rich-text.description.read-view",
      placeholder: "issue.views.field.rich-text.description.placeholder",
      editButton: "issue.views.field.rich-text.description.edit-button",
      saveButton: "issue.views.field.rich-text.description.save-button",
      cancelButton: "issue.views.field.rich-text.description.cancel-button",
    },
    subtasks: {
      container: "issue.views.field.subtasks",
      heading: "issue.views.field.subtasks.heading",
      addButton: "issue.views.field.subtasks.add-button",
      item: (key: string) => `issue.views.field.subtasks.item.${key}`,
    },
    links: {
      container: "issue.views.field.issuelinks",
      heading: "issue.views.field.issuelinks.heading",
      addButton: "issue.views.field.issuelinks.add-button",
      linkType: "issue.views.field.issuelinks.link-type",
      linkTarget: "issue.views.field.issuelinks.target",
      submit: "issue.views.field.issuelinks.submit",
      item: (key: string) => `issue.views.field.issuelinks.item.${key}`,
    },

    // Activity tabs
    activity: {
      container: "issue.activity-feed",
      tab: (name: "all" | "comments" | "history" | "worklog") => `issue.activity-feed.tab.${name}`,
      sort: "issue.activity-feed.sort",
      list: "issue.activity-feed.list",
      addComment: "issue.activity-feed.add-comment",
      commentInput: "issue.activity-feed.add-comment.input",
      commentSubmit: "issue.activity-feed.add-comment.submit",
      commentItem: (id: string) => `issue.activity-feed.comment.${id}`,
      commentEdit: (id: string) => `issue.activity-feed.comment.${id}.edit`,
      commentDelete: (id: string) => `issue.activity-feed.comment.${id}.delete`,
      historyItem: (id: string) => `issue.activity-feed.history.${id}`,
    },

    // Right details panel
    details: {
      container: "issue.views.issue-base.context.context-items",
      heading: "issue.views.issue-base.context.context-items.heading",
      gear: "issue.views.issue-base.context.context-items.gear",
      field: (name: string) => `issue.views.field.${name}`,
      // Per-field handles agents grep on:
      assignee: "issue.views.field.user.assignee",
      assigneeAssignToMe: "issue.views.field.user.assignee.assign-to-me",
      priority: "issue.views.field.priority.priority",
      parent: "issue.views.field.parent.parent",
      dueDate: "issue.views.field.date.duedate",
      labels: "issue.views.field.labels.labels",
      team: "issue.views.field.team.team",
      startDate: "issue.views.field.date.startdate",
      sprint: "issue.views.field.sprint.sprint",
      storyPoints: "issue.views.field.number.customfield_10016",
      reporter: "issue.views.field.user.reporter",
    },

    development: {
      container: "issue.views.issue-base.context.development",
      heading: "issue.views.issue-base.context.development.heading",
    },
  },

  // ------------------------- Generic widgets -------------------------------
  dropdown: {
    trigger: (name: string) => `${name}.trigger`,
    listbox: (name: string) => `${name}.listbox`,
    option: (name: string, value: string) => `${name}.option.${value}`,
  },
  picker: {
    user: (field: string) => `picker.user.${field}`,
    userMenu: (field: string) => `picker.user.${field}.menu`,
    userOption: (field: string, userId: string) => `picker.user.${field}.option.${userId}`,
    userAssignToMe: (field: string) => `picker.user.${field}.assign-to-me`,
  },
} as const;

/**
 * Helper that returns a `data-testid` attribute spread. Use as:
 *   <button {...testId(TESTID.createModal.submit)}>Create</button>
 */
export function testId(value: string): { "data-testid": string } {
  return { "data-testid": value };
}
