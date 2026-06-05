// frontend\src\components\layout\Topbar.jsx
import React, { useState, useEffect } from "react";
import { getUserFromToken } from "../../utils/auth";

const API_URL = import.meta.env.VITE_API_URL;

const formatBarangayLabel = (name) => {
  if (!name) return "";
  const ROMAN = new Set([
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
  ]);
  return name.toLowerCase().replace(/\b\w+/g, (word) => {
    const upper = word.toUpperCase();
    if (ROMAN.has(upper)) return upper;
    if (upper === "P" || upper === "F") return upper;
    return word.charAt(0).toUpperCase() + word.slice(1);
  });
};

const TopBar = ({ onMenuClick }) => {
  const [user, setUser] = useState(null);
  const [profileData, setProfileData] = useState(() => {
    const cached = localStorage.getItem("cachedProfile");
    return cached ? JSON.parse(cached) : null;
  });
  const [profilePicture, setProfilePicture] = useState(() => {
    const cached = localStorage.getItem("cachedProfile");
    if (cached) {
      const parsed = JSON.parse(cached);
      return parsed.profile_picture ? `${API_URL}${parsed.profile_picture}` : null;
    }
    return null;
  });

  useEffect(() => {
    const userData = getUserFromToken();
    setUser(userData);
    fetchProfileData();

    const handleProfileUpdated = () => {
      localStorage.removeItem("cachedProfile");
      fetchProfileData();
    };
    window.addEventListener("profileUpdated", handleProfileUpdated);

    return () => {
      window.removeEventListener("profileUpdated", handleProfileUpdated);
    };
  }, []);

  useEffect(() => {
    const handleFocus = () => fetchProfileData();
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, []);

  const fetchProfileData = async () => {
    try {
      const token = localStorage.getItem("token");
      const cached = localStorage.getItem("cachedProfile");
      if (cached) {
        const parsed = JSON.parse(cached);
        setProfileData(parsed);
        setProfilePicture(parsed.profile_picture ? `${API_URL}${parsed.profile_picture}` : null);
      }
      const response = await fetch(`${API_URL}/users/profile`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        if (data.user) {
          setProfileData(data.user);
          setProfilePicture(data.user.profile_picture ? `${API_URL}${data.user.profile_picture}` : null);
          localStorage.setItem("cachedProfile", JSON.stringify(data.user));
        }
      }
    } catch (error) {
      console.error("Error fetching profile data:", error);
    }
  };

  const getInitials = () => {
    if (!profileData)
      return user?.username ? user.username.substring(0, 2).toUpperCase() : "JI";
    const first = profileData.first_name?.[0] || "";
    const last  = profileData.last_name?.[0]  || "";
    return (first + last).toUpperCase() || "?";
  };

  const getDisplayName = () => {
    if (!profileData) return "User";
    const rank      = profileData.rank_abbreviation ? `${profileData.rank_abbreviation}. ` : "";
    const firstName = profileData.first_name || "";
    const lastName  = profileData.last_name  || "";
    const displayFirst = firstName.length > 15 ? firstName.substring(0, 9) + "..." : firstName;
    const displayLast  = lastName.length  > 15 ? lastName.substring(0, 9)  + "..." : lastName;
    const fullName = displayLast ? `${displayFirst} ${displayLast}` : displayFirst;
    return (rank + fullName).trim() || user?.username || "User";
  };

  return (
    <header className="top-bar">
      <div
        className="top-bar-left"
        style={{ display: "flex", alignItems: "center", gap: "12px" }}
      >
        <button
          className="hamburger-btn"
          onClick={onMenuClick}
          aria-label="Open menu"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <line x1="3" y1="6"  x2="21" y2="6"  />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
      </div>

      <div
        className="top-bar-right"
        style={{ display: "flex", alignItems: "center", gap: "12px" }}
      >
        {/* ── PROFILE ── */}
        <div className="user-profile">
          <div className="user-info">
            <div className="user-name">{getDisplayName()}</div>
            <div className="user-role">
              {profileData?.user_type === "barangay" && profileData?.barangay_code
                ? `${profileData?.role || user?.role} - ${formatBarangayLabel(profileData.barangay_code)}`
                : profileData?.role || user?.role}
            </div>
          </div>
          <div className="user-avatar">
            {profilePicture ? (
              <img
                src={profilePicture}
                alt="Profile"
                style={{
                  width: "100%",
                  height: "100%",
                  borderRadius: "50%",
                  objectFit: "cover",
                }}
              />
            ) : (
              getInitials()
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

export default TopBar;