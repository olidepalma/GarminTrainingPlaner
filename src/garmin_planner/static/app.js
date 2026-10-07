import * as core from "./modules/core.js";
import * as overview from "./modules/overview.js";
import * as auth from "./modules/auth.js";
import * as connections from "./modules/connections.js";
import * as coach from "./modules/coach.js";
import * as statistics from "./modules/statistics.js";
import * as calendar from "./modules/calendar.js";
import * as workouts from "./modules/workouts.js";
import * as review from "./modules/review.js";
import * as library from "./modules/library.js";
core.session.boot = auth.boot;
core.session.refreshLibrary = library.loadLibrary;
core.session.refresh = () =>
  Promise.all([
    overview.loadDashboard(),
    connections.loadConnections(),
    coach.loadCoach(),
    statistics.loadStatistics(),
    calendar.loadCalendar(),
    library.loadLibrary(),
    review.loadReview(),
  ]);
core.init();
overview.init();
auth.init();
connections.init();
coach.init();
statistics.init();
calendar.init();
workouts.init();
review.init();
library.init();
auth.boot().catch((error) => {
  core.$("login-error").textContent = error.message;
});
