import { getApp } from "firebase/app";
import { getAnalytics, isSupported, logEvent, setUserId, setUserProperties, type Analytics } from "firebase/analytics";

let analyticsInstance: Analytics | null = null;

export async function initAnalytics(): Promise<void> {
  if (typeof window === "undefined") return;

  try {
    const supported = await isSupported();
    if (!supported) return;

    if (analyticsInstance) return;

    analyticsInstance = getAnalytics(getApp());

    captureUtmParams(analyticsInstance);
  } catch {
    // Analytics may fail in dev/emulator — silently ignore
  }
}

function captureUtmParams(analytics: Analytics): void {
  const SESSION_KEY = "utm_captured";
  if (sessionStorage.getItem(SESSION_KEY)) return;

  const params = new URLSearchParams(window.location.search);
  const utmSource = params.get("utm_source");
  const utmMedium = params.get("utm_medium");
  const utmCampaign = params.get("utm_campaign");

  if (utmSource ?? utmMedium ?? utmCampaign) {
    logEvent(analytics, "referral_source", {
      ...(utmSource ? { utm_source: utmSource } : {}),
      ...(utmMedium ? { utm_medium: utmMedium } : {}),
      ...(utmCampaign ? { utm_campaign: utmCampaign } : {}),
    });
  }

  sessionStorage.setItem(SESSION_KEY, "1");
}

export function trackEvent(
  name: string,
  params?: Record<string, string | number>,
): void {
  if (!analyticsInstance) return;
  logEvent(analyticsInstance, name, params);
}

export function trackPageView(pagePath: string, pageTitle: string): void {
  trackEvent("page_view", { page_path: pagePath, page_title: pageTitle });
}

export function trackChatSessionStart(params: {
  municipality_code?: string;
  party_ids?: string[];
  scope: string;
}): void {
  trackEvent("chat_session_start", {
    ...(params.municipality_code
      ? { municipality_code: params.municipality_code }
      : {}),
    ...(params.party_ids ? { party_ids: params.party_ids.join(",") } : {}),
    scope: params.scope,
  });
}

export function trackChatMessageSent(params: {
  session_id: string;
  message_length: number;
  has_demographics: boolean;
}): void {
  trackEvent("chat_message_sent", {
    session_id: params.session_id,
    message_length: params.message_length,
    has_demographics: params.has_demographics ? 1 : 0,
  });
}

export function trackDemographicAnswered(params: {
  field: string;
  value: string;
  message_number: number;
}): void {
  trackEvent("demographic_answered", {
    field: params.field,
    value: params.value,
    message_number: params.message_number,
  });
}

export function trackDemographicSkipped(params: {
  field: string;
  message_number: number;
}): void {
  trackEvent("demographic_skipped", {
    field: params.field,
    message_number: params.message_number,
  });
}

export function trackSuggestionClicked(params: {
  question_id: string;
}): void {
  trackEvent("suggestion_clicked", { question_id: params.question_id });
}

export function trackCommunePageView(params: {
  commune_code: string;
  commune_name: string;
}): void {
  trackEvent("commune_page_view", {
    commune_code: params.commune_code,
    commune_name: params.commune_name,
  });
  // Persist last visited commune as a user-level property
  setAnalyticsUserProperties({ last_commune_code: params.commune_code });
}

export function trackElectoralListSelected(params: {
  panel_number: number;
  list_label: string;
}): void {
  trackEvent("electoral_list_selected", {
    panel_number: params.panel_number,
    list_label: params.list_label,
  });
}

export function setAnalyticsUserId(userId: string): void {
  if (!analyticsInstance) return;
  setUserId(analyticsInstance, userId);
}

export function setAnalyticsUserProperties(properties: Record<string, string>): void {
  if (!analyticsInstance) return;
  setUserProperties(analyticsInstance, properties);
}

export function trackLogin(params: { method: string }): void {
  trackEvent("login", { method: params.method });
}

export function trackSignUp(params: { method: string }): void {
  trackEvent("sign_up", { method: params.method });
}

export function trackQuickReplyClicked(params: {
  reply_text: string;
  session_id: string;
}): void {
  trackEvent("quick_reply_clicked", {
    reply_text: params.reply_text.slice(0, 100),
    session_id: params.session_id,
  });
}

export function trackProConRequested(params: {
  session_id: string;
  topic: string;
}): void {
  trackEvent("pro_con_requested", {
    session_id: params.session_id,
    topic: params.topic.slice(0, 100),
  });
}

export function trackVotingBehaviorRequested(params: {
  session_id: string;
  party_id: string;
}): void {
  trackEvent("voting_behavior_requested", {
    session_id: params.session_id,
    party_id: params.party_id,
  });
}

export function trackVotingBehaviorDetailViewed(params: {
  vote_id: string;
  party_id: string;
}): void {
  trackEvent("voting_behavior_detail_viewed", {
    vote_id: params.vote_id,
    party_id: params.party_id,
  });
}

export function trackShareClicked(params: {
  content_type: string;
  session_id?: string;
}): void {
  trackEvent("share", {
    content_type: params.content_type,
    ...(params.session_id ? { session_id: params.session_id } : {}),
  });
}

export function trackSourceClicked(params: {
  source_url: string;
  party_id: string;
}): void {
  trackEvent("source_clicked", {
    source_url: params.source_url.slice(0, 500),
    party_id: params.party_id,
  });
}

export function trackCommuneDashboardView(params: {
  commune_code: string;
  commune_name: string;
  list_count: number;
}): void {
  trackEvent("commune_dashboard_view", {
    commune_code: params.commune_code,
    commune_name: params.commune_name,
    list_count: params.list_count,
  });
}

export function trackInitialSuggestionClicked(params: {
  suggestion_text: string;
}): void {
  trackEvent("initial_suggestion_clicked", {
    suggestion_text: params.suggestion_text.slice(0, 100),
  });
}

export function trackMunicipalitySearched(params: {
  search_term: string;
  result_count: number;
}): void {
  trackEvent("municipality_searched", {
    search_term: params.search_term,
    result_count: params.result_count,
  });
}

export function trackNewChatStarted(params: {
  scope: string;
  party_count: number;
}): void {
  trackEvent("new_chat_started", {
    scope: params.scope,
    party_count: params.party_count,
  });
}

export function trackChatResponseReceived(params: {
  session_id: string;
  party_id: string;
  response_length: number;
  has_sources: boolean;
}): void {
  trackEvent("chat_response_received", {
    session_id: params.session_id,
    party_id: params.party_id,
    response_length: params.response_length,
    has_sources: params.has_sources ? 1 : 0,
  });
}

export function trackErrorOccurred(params: {
  error_type: string;
  error_context?: string;
}): void {
  trackEvent("app_error", {
    error_type: params.error_type,
    ...(params.error_context ? { error_context: params.error_context } : {}),
  });
}

export function trackFeedbackGiven(params: {
  session_id: string;
  message_id: string;
  sentiment: "like" | "dislike";
}): void {
  trackEvent("feedback_given", {
    session_id: params.session_id,
    message_id: params.message_id,
    sentiment: params.sentiment,
  });
}

export function trackMessageCopied(params: {
  session_id: string;
  party_id?: string;
}): void {
  trackEvent("message_copied", {
    session_id: params.session_id,
    ...(params.party_id ? { party_id: params.party_id } : {}),
  });
}

export function trackDonationStarted(params: {
  amount: number;
}): void {
  trackEvent("donation_started", {
    amount: params.amount,
  });
}

export function trackNewsletterSubscribed(): void {
  trackEvent("newsletter_subscribe");
}

export function trackNewsletterUnsubscribed(): void {
  trackEvent("newsletter_unsubscribe");
}

export function trackSecondTourModeViewed(params: {
  commune_code: string;
  mode: "second_tour" | "elected_first_round";
}): void {
  trackEvent("second_tour_mode_viewed", {
    commune_code: params.commune_code,
    mode: params.mode,
  });
}

export function trackCandidateSelectionChanged(params: {
  commune_code: string;
  candidate_id: string;
  action: "added" | "removed";
}): void {
  trackEvent("candidate_selection_changed", {
    commune_code: params.commune_code,
    candidate_id: params.candidate_id,
    action: params.action,
  });
}
