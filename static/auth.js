import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import {
  GoogleAuthProvider,
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
} from "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js";

const app = initializeApp(window.FIREBASE_CONFIG);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();
const userLabel = document.querySelector("#user");
const loginButton = document.querySelector("#login");
const logoutButton = document.querySelector("#logout");
const toggleButton = document.querySelector("#toggle");
const errorMessage = document.querySelector("#error");

window.getIdToken = async () => {
  if (!auth.currentUser) {
    return null;
  }

  return auth.currentUser.getIdToken();
};

onAuthStateChanged(auth, (user) => {
  userLabel.textContent = user?.displayName || user?.email || "";
  userLabel.hidden = !user;
  loginButton.hidden = Boolean(user);
  logoutButton.hidden = !user;
  toggleButton.disabled = !user;
});

loginButton.addEventListener("click", async () => {
  loginButton.disabled = true;
  errorMessage.hidden = true;

  try {
    await signInWithPopup(auth, provider);
  } catch (error) {
    console.error("Googleログインに失敗しました。", error);
    errorMessage.textContent =
      error.code === "auth/unauthorized-domain"
        ? "このドメインはFirebaseの承認済みドメインに登録されていません。"
        : "ログインできませんでした。Firebaseの設定を確認してください。";
    errorMessage.hidden = false;
  } finally {
    loginButton.disabled = false;
  }
});

logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  errorMessage.hidden = true;

  try {
    await signOut(auth);
  } catch (error) {
    console.error("ログアウトに失敗しました。", error);
    errorMessage.textContent = "ログアウトできませんでした。もう一度お試しください。";
    errorMessage.hidden = false;
  } finally {
    logoutButton.disabled = false;
  }
});
