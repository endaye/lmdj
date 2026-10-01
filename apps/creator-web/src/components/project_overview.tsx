import {selectCreatorPhase, type CreatorState} from "../state/creator_state";
import {shortProjectId} from "../state/view_model";

interface ProjectOverviewProps {
  state: CreatorState;
}

export function ProjectOverview({state}: ProjectOverviewProps) {
  const project = state.project.current;
  const phase = selectCreatorPhase(state);
  return (
    <div className="project-overview" data-testid="project-overview">
      <dl className="overview-facts">
        <div>
          <dt>Identity</dt>
          <dd>{project ? shortProjectId(project.projectId) : "none"}</dd>
        </div>
        <div>
          <dt>Load</dt>
          <dd>{state.project.phase}</dd>
        </div>
        <div>
          <dt>Runtime</dt>
          <dd>{state.runtime.phase}</dd>
        </div>
        <div>
          <dt>Creator</dt>
          <dd>{phase}</dd>
        </div>
        {state.runtime.errorCode !== null ? (
          <div>
            <dt>Error</dt>
            {/* The alert carries the message and next step; the code is in
                Developer diagnostics. */}
            <dd>Needs attention</dd>
          </div>
        ) : null}
      </dl>
      <p className="overview-grid-caption">
        Projects save automatically. Duplicate and Project export are not Host actions yet.
      </p>
    </div>
  );
}
