import type { ProductProfile } from "./transport/api";

export function profileHasCriteria(profile: ProductProfile): boolean {
  return profile.tasks.some((task) =>
    task.behaviours.some((behaviour) => behaviour.criteria.length > 0),
  );
}
