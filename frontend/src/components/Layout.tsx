import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

export function Layout() {
  const location = useLocation();

  return (
    <div className="app-shell">
      <header className="hero">
        <div className="hero__content">
          <Link to="/" className="brand">
            <span className="brand__mark">RL</span>
            <span>
              <strong>RepoLens AI</strong>
              <small>Codebase onboarding with grounded citations</small>
            </span>
          </Link>
          <nav className="nav">
            <NavLink to="/" className={({ isActive }) => navClass(isActive)}>
              Home
            </NavLink>
            {location.pathname.includes("/repo/") && (
              <>
                <NavLink
                  to={location.pathname.split("/evals")[0]}
                  className={({ isActive }) => navClass(isActive && !location.pathname.endsWith("/evals"))}
                >
                  Repo
                </NavLink>
                <NavLink
                  to={`${location.pathname.split("/evals")[0]}/evals`}
                  className={({ isActive }) => navClass(isActive || location.pathname.endsWith("/evals"))}
                >
                  Evaluations
                </NavLink>
              </>
            )}
          </nav>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  );
}

function navClass(isActive: boolean): string {
  return `nav__link${isActive ? " nav__link--active" : ""}`;
}

