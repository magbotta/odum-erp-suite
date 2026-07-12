export interface FieldDef {
  name: string;
  type: string;
  label: string;
  required: boolean;
  options: string[] | null;
  target: string | null;
  hidden: boolean;
  read_only: boolean;
}

export interface WorkflowTransition {
  from: string;
  to: string;
  action: string | null;
}

export interface WorkflowDef {
  states: string[];
  initial_state: string;
  transitions: WorkflowTransition[];
}

export interface EntityMeta {
  key: string;
  entity: string;
  app: string;
  label: string;
  label_plural: string;
  snake_name: string;
  api_slug: string;
  api_path: string;
  fields: FieldDef[];
  workflow: WorkflowDef | null;
}
