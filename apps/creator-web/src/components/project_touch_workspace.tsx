import {ProjectSurface} from "./project_surface";

export function ProjectTouchWorkspace(
  props: Omit<Parameters<typeof ProjectSurface>[0], "hideSummary">,
) {
  return <ProjectSurface {...props} hideSummary />;
}
