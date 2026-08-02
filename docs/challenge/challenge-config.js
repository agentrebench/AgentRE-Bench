(function () {
  const config = {
    competitionName: "AgentRE Challenge",
    seasonName: "Season 1",
    tagline: "Stump the Frontier Models",
    prizeAmount: "$500",
    duration: "20 days",
    architecture: "Linux x86-64 ELF",
    analysisMode: "Static analysis",
    maximumBinarySize: "10 MB",
    minimumAcceptedSubmissions: 1,
    maximumEntriesPerEntrant: 3,
    organizerGithubUsername: "agentrebench",
    registrationPageUrl: "/challenge/register/",
    registrationPullRequestUrl: "https://github.com/agentrebench/AgentRE-Bench/compare?quick_pull=1&template=challenge-registration.md",
    registrationManifestUrl: "/challenge/registrations/index.json",
    registrationTemplatePath: "docs/challenge/registrations/template.json",
    privateRepositoryName: "agentre-challenge-entry",
    finalSubmissionTag: "agentre-season-1-final",
    competitionStatus: "open",
    allowedStatuses: ["upcoming", "open", "validation", "judging", "complete", "archived"],
    statusLabels: {
      upcoming: "Upcoming",
      open: "Submissions Open",
      validation: "Validation",
      judging: "Judging",
      complete: "Complete",
      archived: "Archived"
    },
    dates: {
      submissionOpens: "August 2, 2026",
      registrationDeadline: "August 15, 2026, 11:59 PM UTC",
      finalCommitDeadline: "August 15, 2026, 11:59 PM UTC",
      validationDates: "August 16-18, 2026",
      evaluationDates: "August 19-20, 2026",
      winnerAnnouncement: "August 21, 2026"
    },
    timeline: [
      {
        label: "Days 1-14",
        title: "Submissions open",
        dateKey: "submissionOpens",
        dateKeys: ["submissionOpens", "registrationDeadline", "finalCommitDeadline"],
        description: "Entrants build privately, invite the organizer, register by pull request, and push the final submission tag before the deadline."
      },
      {
        label: "Days 15-17",
        title: "Validation and rebuilding",
        dateKey: "validationDates",
        dateKeys: ["validationDates"],
        description: "AgentRE checks eligibility, source availability, reproducibility, checksums, and safety requirements."
      },
      {
        label: "Days 18-19",
        title: "Model evaluations",
        dateKey: "evaluationDates",
        dateKeys: ["evaluationDates"],
        description: "Frontier AI agents perform static reverse engineering against accepted binaries and are scored against private ground truth."
      },
      {
        label: "Day 20",
        title: "Winner announced",
        dateKey: "winnerAnnouncement",
        dateKeys: ["winnerAnnouncement"],
        description: "Public rankings, aggregate scores, awards, and sanitized summaries are published after review."
      }
    ],
    officialModelPanel: [
      "Gemini 3.1 Flash Lite",
      "DeepSeek V4 Pro",
      "Claude Opus 4.8",
      "Kimi K2.6",
      "DeepSeek V4 Flash",
      "GPT-5.5"
    ],
    primaryScoringMetric: {
      name: "Entry difficulty score",
      formula: "100 - average official model correctness",
      description: "The winning binary is the eligible submission that produces the lowest aggregate correctness score across the official Season 1 model panel."
    },
    minimumModelPanelWinsForPrize: 4,
    scoringWeights: [
      {
        name: "Entry difficulty score",
        weight: 100,
        description: "Primary ranking: 100 minus average official model correctness across valid official evaluations."
      }
    ],
    scoreReportingMetrics: [
      "Average official model correctness",
      "Median official model correctness",
      "Entry difficulty score",
      "Official model panel wins",
      "Models below the passing threshold",
      "Complete failures",
      "Invalid or inconclusive runs"
    ],
    tieBreakOrder: [
      "More official model panel wins",
      "Lower median official model correctness",
      "More official models below the passing threshold",
      "Higher manual meaningful reverse-engineering difficulty score",
      "Higher reproducibility score",
      "Earlier frozen submission timestamp"
    ]
  };

  window.AgentREChallengeConfig = config;
})();
