import {
  ArrowDownLeft, ArrowUpRight, Banknote, Briefcase, CircleHelp, Clapperboard, CreditCard, Fuel, GraduationCap,
  HeartPulse, Home, Landmark, Percent, PiggyBank, Plane, Receipt, Scale, Shield, ShoppingBag, ShoppingBasket,
  TrendingUp, Undo2, Utensils, Wallet, Zap, type LucideIcon,
} from "lucide-react";

export const CATEGORY_META: Record<string, { name: string; kind: "income" | "expense" | "transfer"; icon: LucideIcon }> = {
  salary: { name: "Salary & Income", kind: "income", icon: Briefcase },
  interest: { name: "Interest", kind: "income", icon: Percent },
  refund: { name: "Refunds & Reversals", kind: "income", icon: Undo2 },
  transfer_in: { name: "Transfers In", kind: "transfer", icon: ArrowDownLeft },
  cash_deposit: { name: "Cash Deposit", kind: "transfer", icon: PiggyBank },
  transfer_out: { name: "Transfers Out", kind: "transfer", icon: ArrowUpRight },
  food: { name: "Food & Dining", kind: "expense", icon: Utensils },
  groceries: { name: "Groceries", kind: "expense", icon: ShoppingBasket },
  shopping: { name: "Shopping", kind: "expense", icon: ShoppingBag },
  travel: { name: "Travel & Transport", kind: "expense", icon: Plane },
  fuel: { name: "Fuel", kind: "expense", icon: Fuel },
  utilities: { name: "Utilities & Bills", kind: "expense", icon: Zap },
  rent: { name: "Rent & Housing", kind: "expense", icon: Home },
  loan: { name: "Loan & EMI", kind: "expense", icon: Landmark },
  investment: { name: "Investments", kind: "transfer", icon: TrendingUp },
  insurance: { name: "Insurance", kind: "expense", icon: Shield },
  health: { name: "Healthcare", kind: "expense", icon: HeartPulse },
  education: { name: "Education", kind: "expense", icon: GraduationCap },
  entertainment: { name: "Entertainment & Subscriptions", kind: "expense", icon: Clapperboard },
  wallet: { name: "Wallet Top-up", kind: "transfer", icon: Wallet },
  cash_withdrawal: { name: "Cash Withdrawal", kind: "expense", icon: Banknote },
  charges: { name: "Bank Charges & Fees", kind: "expense", icon: Receipt },
  tax: { name: "Taxes", kind: "expense", icon: Scale },
  card_payment: { name: "Credit Card Payment", kind: "transfer", icon: CreditCard },
  other: { name: "Other", kind: "expense", icon: CircleHelp },
};

export const CATEGORY_IDS = Object.keys(CATEGORY_META);

export function catMeta(id: string) {
  return CATEGORY_META[id] ?? CATEGORY_META.other;
}

export const METHOD_LABEL: Record<string, string> = {
  rule: "Rule",
  merchant: "Known merchant",
  ml: "ML model",
  "rule+ml": "Rule · model agrees",
  "merchant+ml": "Merchant · model agrees",
  channel: "Payment-channel rule",
  learned: "Your rule",
  user: "Set by you",
  fallback: "Unsure",
};
