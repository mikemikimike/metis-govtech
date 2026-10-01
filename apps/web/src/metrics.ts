import type { ProductProfile } from "./transport/api";

export function profileHasCriteria(profile: ProductProfile): boolean {
  return profile.features.some((feature) =>
    feature.behaviours.some((behaviour) => behaviour.criteria.length > 0),
  );
}
