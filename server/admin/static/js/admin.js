/**
 * TomatoPlan Admin - JavaScript
 */

// Configuration
const API_BASE = '';  // Même origine
let authToken = localStorage.getItem('tomatoplan_token');

/**
 * Effectue un appel API authentifié
 */
async function apiCall(endpoint, method = 'GET', data = null) {
    const headers = {
        'Content-Type': 'application/json',
    };

    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }

    const options = {
        method,
        headers,
    };

    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }

    const response = await fetch(`${API_BASE}${endpoint}`, options);

    if (response.status === 401) {
        // Token expiré, rediriger vers login
        logout();
        throw new Error('Session expirée');
    }

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Erreur API');
    }

    return response.json();
}

/**
 * Connexion utilisateur
 */
async function login(username, hostname = null) {
    try {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, hostname }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Échec de connexion');
        }

        const data = await response.json();
        authToken = data.access_token;
        localStorage.setItem('tomatoplan_token', authToken);
        localStorage.setItem('tomatoplan_user', JSON.stringify(data.user));

        return data;
    } catch (error) {
        console.error('Erreur login:', error);
        throw error;
    }
}

/**
 * Déconnexion
 */
async function logout() {
    try {
        if (authToken) {
            await fetch(`${API_BASE}/auth/logout`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                },
            });
        }
    } catch (error) {
        console.error('Erreur logout:', error);
    }

    authToken = null;
    localStorage.removeItem('tomatoplan_token');
    localStorage.removeItem('tomatoplan_user');

    // Recharger la page pour afficher le login
    window.location.href = '/admin/login';
}

/**
 * Vérifie si l'utilisateur est connecté
 */
function isAuthenticated() {
    return !!authToken;
}

/**
 * Récupère les infos de l'utilisateur courant
 */
function getCurrentUser() {
    const userData = localStorage.getItem('tomatoplan_user');
    return userData ? JSON.parse(userData) : null;
}

/**
 * Formate une date ISO en format lisible
 */
function formatDate(isoDate) {
    if (!isoDate) return '-';
    const date = new Date(isoDate);
    return date.toLocaleString('fr-FR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

/**
 * Formate une date ISO en format court (date uniquement)
 */
function formatDateShort(isoDate) {
    if (!isoDate) return '-';
    const date = new Date(isoDate);
    return date.toLocaleDateString('fr-FR');
}

/**
 * Affiche un message toast
 */
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        z-index: 3000;
        min-width: 300px;
        animation: slideIn 0.3s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * Ouvre une modal
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

/**
 * Ferme une modal
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

/**
 * Confirme une action
 */
function confirm(message) {
    return window.confirm(message);
}

/**
 * Vérifie le statut du serveur
 */
async function checkServerStatus() {
    try {
        const status = await fetch(`${API_BASE}/health`);
        if (status.ok) {
            const data = await status.json();
            const statusEl = document.getElementById('server-status');
            if (statusEl) {
                statusEl.textContent = `Uptime: ${data.uptime_formatted}`;
                statusEl.style.color = '#27ae60';
            }
            return true;
        }
    } catch (error) {
        const statusEl = document.getElementById('server-status');
        if (statusEl) {
            statusEl.textContent = 'Serveur inaccessible';
            statusEl.style.color = '#e74c3c';
        }
    }
    return false;
}

/**
 * Télécharge un fichier
 */
function downloadFile(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

/**
 * Formate une taille en octets
 */
function formatSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// Initialisation
document.addEventListener('DOMContentLoaded', function() {
    // Afficher l'utilisateur courant
    const user = getCurrentUser();
    const userInfoEl = document.getElementById('current-user');
    if (userInfoEl && user) {
        userInfoEl.textContent = `${user.display_name || user.username} (${user.role})`;
    }

    // Vérifier le statut du serveur
    checkServerStatus();
    setInterval(checkServerStatus, 60000);

    // Fermer les modals en cliquant à l'extérieur
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                closeModal(this.id);
            }
        });
    });
});

// Styles pour les animations toast
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);
