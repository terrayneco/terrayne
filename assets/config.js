// Public config for terrayne.co accounts. The anon key is designed to be public (data is protected by row-level security).
// Fill these in from Supabase > Project Settings > API.
window.TERRAYNE = {
  supabaseUrl: "",      // e.g. "https://wpkfxynevyaxmiikzgsb.supabase.co/rest/v1/"
  supabaseAnonKey: "",  // the "sb_publishable_XhPkpSKRuwGc-Jg2Ka2Jdw_3cqB9-Vk" key
  prices: { investor: { month: 19, year: 190 }, pro: { month: 79, year: 790 }, enterprise: { month: 399, year: 3990 } }
};
