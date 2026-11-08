import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { createClient } from "@supabase/supabase-js";

const url = process.env.LOCAL_SUPABASE_URL ?? "http://127.0.0.1:54321";
const anonKey = process.env.LOCAL_SUPABASE_ANON_KEY;
const inboxUrl = process.env.LOCAL_INBUCKET_URL ?? "http://127.0.0.1:54324";
const fixtureJobId = "00000000-0000-4000-8000-000000000001";

if (!anonKey) throw new Error("LOCAL_SUPABASE_ANON_KEY is required; obtain it from `supabase status`.");
if (!/^https?:\/\/127\.0\.0\.1(?::\d+)?$/.test(url) && !/^https?:\/\/localhost(?::\d+)?$/.test(url)) {
  throw new Error(`Refusing to run local auth tests against non-local URL: ${url}`);
}

const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const email = `ats-sniper-${suffix}@example.com`;
const password = "LocalTest-password-123!";

function client(storage) {
  return createClient(url, anonKey, {
    auth: { autoRefreshToken: false, detectSessionInUrl: false, persistSession: Boolean(storage), storage },
  });
}

async function inboxMessages() {
  const response = await fetch(`${inboxUrl}/api/v1/messages`);
  assert.equal(response.ok, true, `Mailpit was not reachable at ${inboxUrl}`);
  const payload = await response.json();
  return payload.messages ?? payload;
}

async function waitForEmail(recipient, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const messages = await inboxMessages();
    const found = messages.find((message) => {
      const recipients = message.To ?? message.to ?? [];
      return recipients.some((address) => String(address.Address ?? address.address ?? address).includes(recipient));
    });
    if (found) {
      const detail = await fetch(`${inboxUrl}/api/v1/message/${found.ID ?? found.id}`);
      assert.equal(detail.ok, true, "Mailpit message detail was not available");
      return detail.json();
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Timed out waiting for an email to ${recipient}`);
}

function linkFromEmail(message) {
  const body = `${message.HTML ?? message.html ?? ""} ${message.Text ?? message.text ?? ""}`;
  const match = body.match(/https?:\/\/[^\s"<>]+/);
  assert.ok(match, "Expected a link in the local Auth email");
  return match[0].replace(/&amp;/g, "&");
}

async function verifyEmail(supabase, message, type) {
  const link = new URL(linkFromEmail(message));
  const tokenHash = link.searchParams.get("token_hash") ?? link.searchParams.get("token");
  assert.ok(tokenHash, "Expected token_hash in local Auth email link");
  const response = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
  assert.equal(response.error, null, response.error?.message);
  return response.data;
}

before(async () => { await inboxMessages(); });

describe("local Supabase Auth and RLS", () => {
  it("signs up, captures confirmation email, and verifies the account", async () => {
    const result = await client().auth.signUp({ email, password, options: { data: { first_name: "Ada", last_name: "Lovelace" } } });
    assert.equal(result.error, null, result.error?.message);
    assert.equal(result.data.session, null, "Email confirmation should be required locally");
    const verified = await verifyEmail(client(), await waitForEmail(email), "signup");
    assert.ok(verified.user);
  });

  it("logs in, persists a session, then logs out", async () => {
    const storageMap = new Map();
    const storage = {
      getItem: (key) => storageMap.get(key) ?? null,
      setItem: (key, value) => storageMap.set(key, value),
      removeItem: (key) => storageMap.delete(key),
    };
    const first = client(storage);
    const signedIn = await first.auth.signInWithPassword({ email, password });
    assert.equal(signedIn.error, null, signedIn.error?.message);
    assert.ok(signedIn.data.session);
    const restored = await client(storage).auth.getSession();
    assert.ok(restored.data.session, "A new client should restore the persisted session");
    const refreshed = await first.auth.refreshSession();
    assert.equal(refreshed.error, null, refreshed.error?.message);
    assert.ok(refreshed.data.session);
    const loggedOut = await first.auth.signOut();
    assert.equal(loggedOut.error, null, loggedOut.error?.message);
    assert.equal((await client(storage).auth.getSession()).data.session, null);
  });

  it("captures a password-recovery email and changes the password", async () => {
    const recoveryEmail = `ats-sniper-recovery-${suffix}@example.com`;
    const recoveryClient = client();
    const signup = await recoveryClient.auth.signUp({ email: recoveryEmail, password });
    assert.equal(signup.error, null, signup.error?.message);
    await verifyEmail(recoveryClient, await waitForEmail(recoveryEmail), "signup");
    const resetRequest = await recoveryClient.auth.resetPasswordForEmail(recoveryEmail, { redirectTo: "http://127.0.0.1:3000" });
    assert.equal(resetRequest.error, null, resetRequest.error?.message);
    await verifyEmail(recoveryClient, await waitForEmail(recoveryEmail), "recovery");
    const updated = await recoveryClient.auth.updateUser({ password: `${password}-changed` });
    assert.equal(updated.error, null, updated.error?.message);
    const invalid = await client().auth.verifyOtp({ token_hash: "expired-or-invalid-token", type: "recovery" });
    assert.ok(invalid.error, "An invalid recovery token must be rejected");
  });

  it("enforces user-owned RLS rows", async () => {
    const owner = client();
    const ownerLogin = await owner.auth.signInWithPassword({ email, password });
    assert.equal(ownerLogin.error, null, ownerLogin.error?.message);
    const ownerUser = (await owner.auth.getUser()).data.user;
    assert.ok(ownerUser);
    const profile = await owner.from("profiles").select("id, email").eq("id", ownerUser.id).single();
    assert.equal(profile.error, null, profile.error?.message);
    assert.equal(profile.data.id, ownerUser.id);
    const namedProfile = await owner.from("profiles").select("first_name, last_name").eq("id", ownerUser.id).single();
    assert.deepEqual(namedProfile.data, { first_name: "Ada", last_name: "Lovelace" });
    const profileUpdate = await owner.from("profiles").update({ first_name: "Grace", last_name: "Hopper" }).eq("id", ownerUser.id);
    assert.equal(profileUpdate.error, null, profileUpdate.error?.message);
    const updatedProfile = await owner.from("profiles").select("first_name, last_name").eq("id", ownerUser.id).single();
    assert.deepEqual(updatedProfile.data, { first_name: "Grace", last_name: "Hopper" });
    const preferences = await owner.from("user_preferences").upsert({
      user_id: ownerUser.id,
      target_roles: ["Data Scientist"],
      target_locations: ["Paris"],
      onboarding_completed_at: new Date().toISOString(),
    });
    assert.equal(preferences.error, null, preferences.error?.message);
    const saved = await owner.from("user_job_status").upsert({ user_id: ownerUser.id, job_id: fixtureJobId, status: "saved", application_status: "to_review" });
    assert.equal(saved.error, null, saved.error?.message);
    const application = await owner.from("user_job_status").update({ application_status: "applied", notes: "Integration test" }).eq("user_id", ownerUser.id).eq("job_id", fixtureJobId);
    assert.equal(application.error, null, application.error?.message);
    const badPassword = await owner.auth.signInWithPassword({ email, password: "Wrong-password-123!" });
    assert.ok(badPassword.error, "An incorrect current password must be rejected");
    const insert = await owner.from("user_job_status").upsert({ user_id: ownerUser.id, job_id: fixtureJobId, status: "saved" });
    assert.equal(insert.error, null, insert.error?.message);
    const ownerRead = await owner.from("user_job_status").select("job_id, status").eq("job_id", fixtureJobId);
    assert.equal(ownerRead.error, null, ownerRead.error?.message);
    assert.equal(ownerRead.data.length, 1);

    const otherEmail = `ats-sniper-other-${suffix}@example.com`;
    const other = client();
    const otherSignup = await other.auth.signUp({ email: otherEmail, password });
    assert.equal(otherSignup.error, null, otherSignup.error?.message);
    await verifyEmail(other, await waitForEmail(otherEmail), "signup");
    const otherLogin = await other.auth.signInWithPassword({ email: otherEmail, password });
    assert.equal(otherLogin.error, null, otherLogin.error?.message);
    const otherRead = await other.from("user_job_status").select("job_id, status").eq("job_id", fixtureJobId);
    assert.equal(otherRead.error, null, otherRead.error?.message);
    assert.equal(otherRead.data.length, 0, "A user must not read another user's status row");
    const otherProfile = await other.from("profiles").select("first_name, last_name").eq("id", (await other.auth.getUser()).data.user.id).single();
    assert.equal(otherProfile.error, null, otherProfile.error?.message);
    assert.deepEqual(otherProfile.data, { first_name: null, last_name: null }, "Existing accounts without names remain valid");
    const ownerProfileFromOther = await other.from("profiles").select("id").eq("id", ownerUser.id);
    assert.equal(ownerProfileFromOther.error, null, ownerProfileFromOther.error?.message);
    assert.equal(ownerProfileFromOther.data.length, 0, "A user must not read another user's profile");
    const otherPreferences = await other.from("user_preferences").select("user_id").eq("user_id", ownerUser.id);
    assert.equal(otherPreferences.error, null, otherPreferences.error?.message);
    assert.equal(otherPreferences.data.length, 0, "A user must not read another user's preferences");
  });
});
