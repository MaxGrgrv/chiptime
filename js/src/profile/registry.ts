/**
 * Known-vendor developer-field registry (taxonomy #22d).
 *
 * Twin of `python/src/chiptime/profile/registry.py`. Hand-ported rather than
 * generated: eight rows that grow by human research, and the two languages want
 * independent edits when a vendor is added mid-investigation.
 *
 * Vendor identity comes from `developer_data_id.manufacturer_id` (stable across app
 * builds, unlike application UUIDs). A (vendor, normalized field name) match promotes
 * the field to a canonical stream name for the semantic layer. Growing this table is
 * an M4 workstream.
 */

export interface VendorField {
  readonly canonicalName: string;
  readonly units: string | null;
}

/**
 * Python keys this on a `(vendor, field_name)` tuple. TypeScript has no tuple keys
 * for object lookup, so the pair is joined with a space -- safe because vendor names
 * are enum identifiers with no spaces, making the split point unambiguous.
 */
const KNOWN_VENDOR_FIELDS: Readonly<Record<string, VendorField>> = Object.freeze({
  "stryd power": { canonicalName: "running_power", units: "W" },
  "stryd leg spring stiffness": { canonicalName: "leg_spring_stiffness", units: "kN/m" },
  "stryd form power": { canonicalName: "form_power", units: "W" },
  "stryd air power": { canonicalName: "air_power", units: "W" },
  "greenteg core temperature": { canonicalName: "core_temperature", units: "C" },
  "greenteg skin temperature": { canonicalName: "skin_temperature", units: "C" },
  "moxy smo2": { canonicalName: "smo2", units: "percent" },
  "moxy thb": { canonicalName: "thb", units: "g/dl" },
});

export function lookup(vendor: string | null, fieldName: string | null): VendorField | null {
  if (vendor === null || fieldName === null) return null;
  return KNOWN_VENDOR_FIELDS[`${vendor} ${fieldName.trim().toLowerCase()}`] ?? null;
}
