import type { AgentName } from "../types";

export interface AgentMeta {
  name: AgentName;
  title: string;
  /** How this colleague talks about their work. */
  voice: string;
  /** One soft color per agent: accent for dots/borders, tint for the seat. */
  accent: string;
  tint: string;
  initial: string;
}

export const AGENTS: Record<AgentName, AgentMeta> = {
  boss: {
    name: "boss", title: "Boss", voice: "Decides", initial: "B",
    accent: "#2f5d62", tint: "#eef4f4",
  },
  inventory: {
    name: "inventory", title: "Inventory", voice: "Counts the shelves", initial: "I",
    accent: "#5b8a5f", tint: "#f0f6f0",
  },
  accounting: {
    name: "accounting", title: "Accounting", voice: "Weighs the money", initial: "A",
    accent: "#a87a2c", tint: "#fbf5ea",
  },
  facilities: {
    name: "facilities", title: "Facilities", voice: "Keeps the space", initial: "F",
    accent: "#5a74a6", tint: "#f0f3fa",
  },
  customer_service: {
    name: "customer_service", title: "Customer Service", voice: "Writes to customers", initial: "C",
    accent: "#b0627a", tint: "#fbf0f4",
  },
};

export const SEAT_ORDER: AgentName[] = ["inventory", "accounting", "facilities", "customer_service"];

export const agentTitle = (name: string | undefined): string =>
  (name && name in AGENTS ? AGENTS[name as AgentName].title : name) ?? "someone";

const TOOL_LABELS: Record<string, string> = {
  list_open_tickets: "listed tickets",
  get_ticket: "read the ticket",
  check_stock: "checked stock",
  quote_bulk_order: "quoted the bulk order",
  find_restock_vendors: "looked for vendors",
  get_bills_and_cash: "checked bills & cash",
  get_invoice: "read the invoice",
  get_lease: "read the lease",
  check_margin: "checked the margin",
  draft_customer_message: "saved a draft",
  request_payment: "asked you to pay",
  request_purchase_order: "asked you to order",
  record_decision: "recorded the decision",
  delegate: "handed off",
};

export const toolLabel = (tool: string): string => TOOL_LABELS[tool] ?? tool.replace(/_/g, " ");

export const TICKET_TYPE_LABEL: Record<string, string> = {
  customer_order: "Customer order",
  rent_notice: "Rent notice",
  price_override: "Price request",
};
