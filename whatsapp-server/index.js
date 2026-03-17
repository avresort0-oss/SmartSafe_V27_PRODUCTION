/**
 * SmartSafe V27 - WhatsApp Node.js Server
 * Built on Express + Baileys (WhiskeySockets)
 * Provides REST API for Python GUI
 */

const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const pino = require('pino');
const QRCode = require('qrcode');
const fs = require('fs-extra');
const path = require('path');
const pkg = require('./package.json'); \nconst Agent = require('agentkeepalive'); \n\nconst { Queue } = require('bullmq'); \nconst { createClient } = require('redis'); \nconst rateLimit = require('express-rate-limit'); \n\nconst REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379'; \nconst redisConnection = createClient({ url: REDIS_URL }); \nredisConnection.connect().catch(console.error); \n\nconst messageQueue = new Queue('whatsapp-messages', { \n    connection: redisConnection, \n    defaultJobOptions: { \n        attempts: 3, \n        backoff: { type: 'exponential', delay: 2000 }, \n        removeOnComplete: true\n }\n }); \n\n// Load environment variables from .env if present (project root preferred).
// This keeps Node and Python configs aligned when using a shared .env file.
try {
    const dotenv = require('dotenv');
    const envPaths = [
        path.join(__dirname, '..', '.env'),
        path.join(__dirname, '.env'),
    ];
    for (const envPath of envPaths) {
        if (fs.existsSync(envPath)) {
            dotenv.config({ path: envPath });
            break;
        }
    }
} catch (err) {
    // No-op: dotenv is optional at runtime
}

const {
    makeWASocket,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    Browsers,
    DisconnectReason,
} = require('@whiskeysockets/baileys');

const app = express();
const PORT = process.env.PORT || 4000;
const APP_VERSION = pkg.version || '1.0.0';
const API_KEY = process.env.SMARTSAFE_API_KEY || '';
const REQUIRE_API_KEY = (process.env.SMARTSAFE_REQUIRE_API_KEY || 'false').toLowerCase() === 'true';
const CORS_ORIGINS = (process.env.SMARTSAFE_CORS_ORIGINS || '')
    .split(',')
    .map((o) => o.trim())
    .filter(Boolean);

// HTTP Agent for connection pooling
const keepAliveAgent = new Agent({
    maxSockets: 100,
    maxFreeSockets: 10,
    timeout: 60000,
    freeSocketTimeout: 30000,
});

// Middleware
app.use(
    cors({
        origin: (origin, callback) => {
            if (!CORS_ORIGINS.length || !origin) {
                return callback(null, true);
            }
            if (CORS_ORIGINS.includes(origin)) {
                return callback(null, true);
            }
            return callback(new Error('Not allowed by CORS'));
        },
        credentials: true,
    })
);
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

// Optional API key guard
app.use((req, res, next) => {
    if (REQUIRE_API_KEY && !['/health', '/stats'].includes(req.path)) {
        const headerKey = req.header('x-api-key');
        if (!headerKey || headerKey !== API_KEY) {
            return res.status(401).json({ ok: false, error: 'Unauthorized', code: 'UNAUTHORIZED' });
        }
    }
    next();
});

// Logging - Use pino logger for Baileys compatibility (without pino-pretty transport)
const logger = pino({
    level: 'info'
});

// Global state
const sessions = new Map();
const stores = new Map();
const SESSION_DIR = path.join(__dirname, 'sessions');
const MESSAGE_STORE_FILE = path.join(SESSION_DIR, 'message_store.json');

// Ensure session directory exists
fs.ensureDirSync(SESSION_DIR);

// Helper: Simple in-memory message store for tracking
const messageStore = new Map();

// Per-account lightweight metrics for UI dashboards and stats
const accountMetrics = new Map();

function normalizeAccount(value) {
    const raw = (value || '').toString().trim();
    return raw || 'default';
}

function getMetrics(account) {
    const key = normalizeAccount(account);
    let entry = accountMetrics.get(key);
    if (!entry) {
        entry = {
            messages_sent: 0,
            profile_checks: 0,
            errors: 0,
            last_error: null,
            last_sent_at: null,
            last_profile_check_at: null,
        };
        accountMetrics.set(key, entry);
    }
    return entry;
}

function logoutAccount(account) {
    const key = normalizeAccount(account);
    const sock = sessions.get(key);
    if (sock) {
        try { sock.logout(); } catch (e) { }
        try { sock.end(undefined); } catch (e) { }
        sessions.delete(key);
    }
    return key;
}

// Load persisted tracked messages (best-effort)
try {
    if (fs.existsSync(MESSAGE_STORE_FILE)) {
        const saved = fs.readJsonSync(MESSAGE_STORE_FILE);
        if (Array.isArray(saved)) {
            for (const msg of saved) {
                if (msg?.id) {
                    messageStore.set(msg.id, msg);
                }
            }
        }
    }
} catch (e) {
    logger.warn('Failed to load persisted message store', e);
}

const persistMessages = () => {
    try {
        fs.writeJsonSync(MESSAGE_STORE_FILE, Array.from(messageStore.values()), { spaces: 2 });
    } catch (e) {
        logger.warn('Failed to persist message store', e);
    }
};

// Per-account lightweight store (contacts + chats) with JSON persistence
function getStore(account) {
    let entry = stores.get(account);
    if (entry) return entry;

    const storePath = path.join(SESSION_DIR, account, 'store.json');
    let data = { contacts: {}, chats: [] };
    if (fs.existsSync(storePath)) {
        try {
            data = fs.readJsonSync(storePath);
        } catch (e) {
            logger.warn(`Failed to load store for ${account}`, e);
        }
    }

    const persist = () => {
        try {
            fs.writeJsonSync(storePath, data, { spaces: 2 });
        } catch (e) {
            logger.warn(`Failed to persist store for ${account}`, e);
        }
    };

    entry = { data, storePath, persist };
    stores.set(account, entry);
    return entry;
}

// Health check
app.get('/health', (req, res) => {
    res.json({
        ok: true,
        status: 'online',
        version: APP_VERSION,
        host: req.hostname || '127.0.0.1',
        port: Number(PORT),
        timestamp: new Date().toISOString()
    });
});

// Get server stats
app.get('/stats', (req, res) => {
    const sessionStats = {};
    const stats = {};
    let currentAccount = null;
    sessions.forEach((sock, name) => {
        const connected = sock?.user ? true : false;
        sessionStats[name] = {
            connected,
            user: sock?.user ? sock.user.id : null
        };

        const metrics = getMetrics(name);
        stats[name] = {
            connected,
            status: connected ? 'READY' : 'DISCONNECTED',
            messages_sent: metrics.messages_sent,
            profile_checks: metrics.profile_checks,
            errors: metrics.errors,
            last_error: metrics.last_error,
            last_sent_at: metrics.last_sent_at,
            last_profile_check_at: metrics.last_profile_check_at,
        };

        if (!currentAccount && connected) {
            currentAccount = name;
        }
    });

    if (!currentAccount) {
        const first = sessions.keys().next();
        currentAccount = first && !first.done ? first.value : 'default';
    }

    res.json({
        ok: true,
        connected: sessions.size > 0,
        total_sessions: sessions.size,
        sessions: sessionStats,
        stats,
        current_account: currentAccount,
        queue_length: await messageQueue.getWaitingCount() + await messageQueue.getActiveCount(),
        server_time: new Date().toISOString()
    });
});

// Get all accounts
app.get('/accounts', (req, res) => {
    const accounts = [];
    let currentAccount = null;
    sessions.forEach((sock, name) => {
        const connected = sock?.user ? true : false;
        if (!currentAccount && connected) {
            currentAccount = name;
        }
        accounts.push({
            account: name,
            name: name,
            label: name,
            connected,
            phone: sock?.user?.id ? sock.user.id.replace('@s.whatsapp.net', '') : null
        });
    });
    if (!currentAccount) {
        currentAccount = accounts.length ? accounts[0].name : 'default';
    }
    res.json({ ok: true, accounts, current_account: currentAccount });
});

// Get accounts status
app.get('/accounts-status', (req, res) => {
    const status = {};
    sessions.forEach((sock, name) => {
        status[name] = {
            connected: sock?.user ? true : false,
            ready: sock?.ws?.readyState === 'open'
        };
    });
    res.json({ ok: true, status, accounts: status });
});

// Status for specific account
app.get('/status', (req, res) => {
    const requested = req.query.account;
    let account = normalizeAccount(requested);
    if (!requested) {
        // Pick the first connected account, then fallback to any session/default.
        for (const [name, sock] of sessions) {
            if (sock?.user) {
                account = name;
                break;
            }
        }
        if (!account || account === 'default') {
            const first = sessions.keys().next();
            account = first && !first.done ? first.value : 'default';
        }
    }

    const sock = sessions.get(account);
    if (!sock) {
        return res.json({
            ok: false,
            error: 'Account not connected',
            code: 'ACCOUNT_NOT_CONNECTED',
            account,
            connected: false,
            status: 'DISCONNECTED'
        });
    }

    const connected = sock?.user ? true : false;
    const phone = sock?.user?.id?.replace('@s.whatsapp.net', '') || null;

    res.json({
        ok: true,
        account,
        status: connected ? 'READY' : 'DISCONNECTED',
        connected,
        user: sock?.user?.id || null,
        phone,
        number: phone,
        device: {
            number: phone,
            model: sock?.user?.device || null,
            platform: sock?.user?.platform || null,
            login_time: null,
            last_sync: null,
        },
    });
});

// Generate QR for account
app.get('/qr/:account?', async (req, res) => {
    const account = normalizeAccount(req.params.account || req.query.account);

    const sock = sessions.get(account);
    if (!sock) {
        return res.json({ ok: false, error: 'Session not initialized' });
    }

    try {
        // Check if already connected
        if (sock.user) {
            return res.json({
                ok: true,
                account,
                connected: true,
                qr: null,
                message: 'Already connected'
            });
        }

        // Generate QR from existing connection if available
        const qr = sock.qr || '';
        if (qr) {
            // Generate QR image
            try {
                const qrImage = await QRCode.toDataURL(qr);
                return res.json({
                    ok: true,
                    account,
                    connected: false,
                    qr: qrImage,
                    qr_raw: qr,
                    message: 'Scan QR code with WhatsApp'
                });
            } catch (e) {
                return res.json({
                    ok: true,
                    account,
                    connected: false,
                    qr_raw: qr,
                    message: 'Scan QR code with WhatsApp'
                });
            }
        }

        res.json({ ok: false, account, error: 'No QR available yet' });
    } catch (err) {
        res.json({ ok: false, account, error: err.message });
    }
});

// Create/update account session
app.post('/connect/:account', async (req, res) => {
    const account = normalizeAccount(req.params.account);

    if (sessions.has(account)) {
        const sock = sessions.get(account);
        if (sock && sock.user) {
            return res.json({ ok: true, account, connected: true, message: 'Already connected' });
        }

        // A connection is already in progress. The client should check for QR/status separately.
        // This avoids creating a duplicate session which can cause race conditions.
        return res.json({ ok: true, account, status: 'pending', message: 'Connection already in progress.' });
    }

    try {
        await createSession(account, res);
    } catch (err) {
        res.status(500).json({ ok: false, error: err.message, code: "CREATE_SESSION_ERROR" });
    }
});

// Reset account session
app.post('/reset/:account', async (req, res) => {
    const account = normalizeAccount(req.params.account);

    try {
        // Close existing session
        const sock = sessions.get(account);
        if (sock) {
            try { sock.end(undefined); } catch (e) { }
            sessions.delete(account);
        }

        // Delete session files
        const sessionPath = path.join(SESSION_DIR, account);
        if (fs.existsSync(sessionPath)) {
            fs.removeSync(sessionPath);
        }

        // Create new session
        await createSession(account, res);
    } catch (err) {
        res.json({ ok: false, error: err.message });
    }
});

// Set active account
app.post('/set-account', (req, res) => {
    const { account } = req.body;
    if (!account) {
        return res.json({ ok: false, error: 'Account required' });
    }

    const normalized = normalizeAccount(account);
    if (!sessions.has(normalized)) {
        return res.json({ ok: false, error: 'Account not connected' });
    }

    res.json({ ok: true, account: normalized });
});

// Logout account
app.get('/logout', (req, res) => {
    const account = logoutAccount(req.query.account);
    res.json({ ok: true, account, message: 'Logged out' });
});

// Logout account (POST alias for compatibility)
app.post('/logout', (req, res) => {
    const account = logoutAccount(req.body?.account || req.query?.account);
    res.json({ ok: true, account, message: 'Logged out' });
});

// Send message
app.post('/send', async (req, res) => {
    const { number, message, account, media_url, messageId } = req.body;

    if (!number) {
        return res.json({ ok: false, error: 'Number required' });
    }

    const accountName = normalizeAccount(account);
    const metrics = getMetrics(accountName);
    const sock = sessions.get(accountName);
    if (!sock || !sock.user) {
        metrics.errors += 1;
        metrics.last_error = 'Not connected';
        return res.json({
            ok: false,
            error: 'Not connected',
            code: 'ACCOUNT_NOT_CONNECTED',
            connected: false,
            account: accountName,
            number
        });
    }

    try {
        const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;

        let sentMsg = null;

        // Prepare message options
        const msgOptions = {};
        if (message) msgOptions.text = message;

        if (media_url) {
            // Send media message - detect type from URL or data URL
            if (media_url.startsWith('data:')) {
                const mime = media_url.split(';')[0].replace('data:', '').toLowerCase();
                if (mime.startsWith('image/')) {
                    msgOptions.image = { url: media_url };
                } else if (mime.startsWith('video/')) {
                    msgOptions.video = { url: media_url };
                } else if (mime.startsWith('audio/')) {
                    msgOptions.audio = { url: media_url };
                } else {
                    msgOptions.document = { url: media_url };
                }
            } else if (media_url.match(/\.(jpg|jpeg|png|gif|webp)$/i)) {
                msgOptions.image = { url: media_url };
            } else if (media_url.match(/\.(mp4|webm|3gp)$/i)) {
                msgOptions.video = { url: media_url };
            } else if (media_url.match(/\.(mp3|wav|ogg|opus)$/i)) {
                msgOptions.audio = { url: media_url };
            } else {
                msgOptions.document = { url: media_url };
            }
        }

        sentMsg = await sock.sendMessage(jid, msgOptions);

        const resultMsgId = sentMsg?.key?.id || messageId || Date.now().toString();

        // Store message for tracking
        messageStore.set(resultMsgId, {
            id: resultMsgId,
            to: number,
            phoneNumber: number,
            content: message,
            status: 'sent',
            account: accountName,
            timestamp: Date.now()
        });
        persistMessages();

        metrics.messages_sent += 1;
        metrics.last_sent_at = Date.now();

        res.json({
            ok: true,
            account: accountName,
            number,
            messageId: resultMsgId,
            message_id: resultMsgId,
            status: 'sent',
            timestamp: Date.now()
        });
    } catch (err) {
        logger.error('Send error:', err);
        metrics.errors += 1;
        metrics.last_error = err.message;
        res.json({ ok: false, error: err.message, account: accountName, number });
    }
});

// Send bulk messages
app.post('/send-bulk', async (req, res) => {
    const { messages, account } = req.body;

    if (!messages || !Array.isArray(messages)) {
        return res.json({ ok: false, error: 'Messages array required' });
    }

    const accountName = normalizeAccount(account);
    const metrics = getMetrics(accountName);
    const sock = sessions.get(accountName);
    if (!sock || !sock.user) {
        metrics.errors += 1;
        metrics.last_error = 'Not connected';
        return res.json({
            ok: false,
            error: 'Not connected',
            code: 'ACCOUNT_NOT_CONNECTED',
            connected: false,
            account: accountName
        });
    }

    const results = [];

    for (const msg of messages) {
        try {
            const jid = msg.number.includes('@') ? msg.number : `${msg.number}@s.whatsapp.net`;
            const sent = await sock.sendMessage(jid, { text: msg.message || '' });
            const resultMsgId = sent?.key?.id || Date.now().toString();
            messageStore.set(resultMsgId, {
                id: resultMsgId,
                to: msg.number,
                phoneNumber: msg.number,
                content: msg.message || '',
                status: 'sent',
                account: accountName,
                timestamp: Date.now()
            });
            persistMessages();
            metrics.messages_sent += 1;
            metrics.last_sent_at = Date.now();
            results.push({
                number: msg.number,
                ok: true,
                account: accountName,
                messageId: resultMsgId,
                message_id: resultMsgId
            });
        } catch (err) {
            metrics.errors += 1;
            metrics.last_error = err.message;
            results.push({
                number: msg.number,
                ok: false,
                account: accountName,
                error: err.message
            });
        }
    }

    const success = results.filter(r => r.ok).length;
    res.json({
        ok: true,
        account: accountName,
        sent: success,
        failed: results.length - success,
        results
    });
});

// Profile check
app.post('/profile-check', async (req, res) => {
    const { number, account } = req.body;

    if (!number) {
        return res.json({ ok: false, error: 'Number required' });
    }

    const accountName = normalizeAccount(account);
    const metrics = getMetrics(accountName);
    const sock = sessions.get(accountName);
    if (!sock || !sock.user) {
        metrics.errors += 1;
        metrics.last_error = 'Not connected';
        return res.json({
            ok: false,
            error: 'Not connected',
            code: 'ACCOUNT_NOT_CONNECTED',
            connected: false,
            account: accountName
        });
    }

    try {
        const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;
        const [exists] = await sock.onWhatsApp(jid);

        metrics.profile_checks += 1;
        metrics.last_profile_check_at = Date.now();

        res.json({
            ok: true,
            exists: exists?.exists || false,
            number: number,
            account: accountName
        });
    } catch (err) {
        metrics.errors += 1;
        metrics.last_error = err.message;
        res.json({ ok: false, error: err.message, account: accountName });
    }
});

// Bulk profile check
app.post('/profile-check-bulk', async (req, res) => {
    const { numbers, account } = req.body;

    if (!numbers || !Array.isArray(numbers)) {
        return res.json({ ok: false, error: 'Numbers array required' });
    }

    const accountName = normalizeAccount(account);
    const metrics = getMetrics(accountName);
    const sock = sessions.get(accountName);
    if (!sock || !sock.user) {
        metrics.errors += 1;
        metrics.last_error = 'Not connected';
        return res.json({
            ok: false,
            error: 'Not connected',
            code: 'ACCOUNT_NOT_CONNECTED',
            connected: false,
            account: accountName
        });
    }

    try {
        const results = [];

        for (const number of numbers) {
            try {
                const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;
                const [exists] = await sock.onWhatsApp(jid);
                metrics.profile_checks += 1;
                metrics.last_profile_check_at = Date.now();
                results.push({
                    number: number,
                    exists: exists?.exists || false,
                    account: accountName
                });
            } catch (err) {
                metrics.errors += 1;
                metrics.last_error = err.message;
                results.push({
                    number: number,
                    exists: false,
                    account: accountName,
                    error: err.message
                });
            }
        }

        res.json({ ok: true, account: accountName, results });
    } catch (err) {
        metrics.errors += 1;
        metrics.last_error = err.message;
        res.json({ ok: false, error: err.message, account: accountName });
    }
});

// Message tracking endpoints
app.post('/track-message', (req, res) => {
    const { messageId, phoneNumber, content, account } = req.body;

    if (!messageId || !phoneNumber) {
        return res.json({ ok: false, error: 'messageId and phoneNumber required' });
    }

    const accountName = normalizeAccount(account);
    messageStore.set(messageId, {
        id: messageId,
        to: phoneNumber,
        phoneNumber,
        content: content,
        status: 'sent',
        account: accountName,
        timestamp: Date.now()
    });
    persistMessages();

    res.json({ ok: true, messageId, account: accountName });
});

app.post('/message-status/:messageId', (req, res) => {
    const { messageId } = req.params;
    const { status } = req.body;

    const msg = messageStore.get(messageId);
    if (!msg) {
        return res.json({ ok: false, error: 'Message not found' });
    }

    msg.status = status;
    msg.updatedAt = Date.now();
    messageStore.set(messageId, msg);
    persistMessages();

    res.json({ ok: true });
});

app.get('/incoming-messages', (req, res) => {
    const { since } = req.query;
    // For now, return empty - can be enhanced with event-based incoming message storage
    res.json({ ok: true, messages: [] });
});

app.get('/message/:messageId', (req, res) => {
    const { messageId } = req.params;
    const msg = messageStore.get(messageId);

    if (!msg) {
        return res.json({ ok: false, error: 'Message not found' });
    }

    res.json({ ok: true, ...msg });
});

app.get('/tracked-messages', (req, res) => {
    const messages = Array.from(messageStore.values());
    res.json({ ok: true, messages });
});

// Get chat list
app.get('/chat-list', (req, res) => {
    const account = normalizeAccount(req.query.account);
    const sock = sessions.get(account);

    if (!sock || !sock.user) {
        return res.json({ ok: false, error: 'Not connected' });
    }

    const entry = stores.get(account);
    if (!entry) {
        return res.json({ ok: true, chats: [] });
    }

    const chats = (entry.data.chats || []).map((chat) => ({
        id: chat.id,
        name: chat.name || chat.subject || '',
        pushname: chat.name || chat.subject || chat.notify || '',
        t: chat.conversationTimestamp || chat.t || chat.lastMessageTimestamp || null,
        count: chat.unreadCount || chat.unread || chat.count || 0,
        unreadCount: chat.unreadCount || chat.unread || chat.count || 0,
        isGroup: !!(chat.id && chat.id.endsWith('@g.us')),
    }));

    res.json({ ok: true, chats });
});

// Get all contacts
app.get('/all-contacts', (req, res) => {
    const account = normalizeAccount(req.query.account);
    const sock = sessions.get(account);

    if (!sock || !sock.user) {
        return res.json({ ok: false, error: 'Not connected' });
    }

    const entry = stores.get(account);
    if (!entry) {
        return res.json({ ok: true, contacts: [] });
    }

    const contacts = Object.values(entry.data.contacts || {}).map((c) => ({
        id: c.id,
        name: c.name || c.notify || '',
        verifiedName: c.verifiedName || null,
        isBusiness: c.biz || false,
    }));

    res.json({ ok: true, contacts });
});

// Start all accounts
app.post('/start-all', async (req, res) => {
    // Check for configured accounts
    const accountsFile = path.join(__dirname, '..', 'accounts_config.json');
    let accounts = ['default'];

    if (fs.existsSync(accountsFile)) {
        try {
            const config = JSON.parse(fs.readFileSync(accountsFile, 'utf8'));
            accounts = Object.keys(config.accounts || {}).length > 0
                ? Object.keys(config.accounts)
                : ['default'];
        } catch (e) {
            accounts = ['default'];
        }
    }

    let started = 0;
    for (const account of accounts) {
        if (!sessions.has(account)) {
            try {
                await createSession(account, null, true);
                started++;
            } catch (e) {
                logger.error(`Failed to start ${account}:`, e);
            }
        }
    }

    res.json({ ok: true, started: started, total: accounts.length });
});

// Create session function
async function createSession(account, res, silent = false) {
    const sessionPath = path.join(SESSION_DIR, account);
    fs.ensureDirSync(sessionPath);

    const { state, saveCreds } = await useMultiFileAuthState(sessionPath);
    const entry = getStore(account);
    const { data, storePath, persist } = entry;

    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        auth: state,
        logger: logger,
        browser: Browsers.appropriate('Desktop'),
        connectTimeoutMs: 60000,
        keepAliveIntervalMs: 30000,
        version,
        printQRInTerminal: false, // we return QR via API instead
    });

    // Store QR when generated
    sock.qr = '';

    sock.ev.on('creds.update', saveCreds);

    // Capture contacts and chats for /all-contacts and /chat-list
    sock.ev.on('contacts.upsert', (contacts) => {
        contacts.forEach((c) => {
            if (!c?.id) return;
            data.contacts[c.id] = { ...data.contacts[c.id], ...c };
        });
        persist();
    });

    sock.ev.on('chats.upsert', (chats) => {
        chats.forEach((chat) => {
            const idx = data.chats.findIndex((c) => c.id === chat.id);
            if (idx >= 0) {
                data.chats[idx] = { ...data.chats[idx], ...chat };
            } else {
                data.chats.push(chat);
            }
        });
        persist();
    });

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            sock.qr = qr;
            if (!silent && res) {
                try {
                    const qrImage = await QRCode.toDataURL(qr);
                    res.json({
                        ok: true,
                        account,
                        qr: qrImage,
                        qr_raw: qr,
                        message: 'Scan QR code with WhatsApp'
                    });
                } catch (e) {
                    res.json({
                        ok: true,
                        account,
                        qr_raw: qr,
                        message: 'Scan QR code with WhatsApp'
                    });
                }
            }
        }

        if (connection === 'close') {
            const reason = lastDisconnect?.error?.output?.statusCode || lastDisconnect?.error?.status;
            const shouldReconnect = reason !== DisconnectReason.loggedOut;

            logger.info(`Connection closed for ${account}: ${reason}`);
            persist();

            if (shouldReconnect) {
                // On reconnect, don't pass the 'res' object from the original request.
                createSession(account, null, silent);
            } else {
                sessions.delete(account);
            }
        } else if (connection === 'open') {
            logger.info(`Connected: ${account}`);
            sessions.set(account, sock);
            // Ensure metrics entry exists for this account
            getMetrics(account);
            persist();

            if (!silent && res) {
                res.json({
                    ok: true,
                    account,
                    connected: true,
                    user: sock.user.id
                });
            }
        }
    });

    sessions.set(account, sock);

    return sock;
}

// Error handling middleware
app.use((err, req, res, next) => {
    logger.error('Server error:', err);
    res.status(500).json({ ok: false, error: err.message });
});

// Start server
app.listen(PORT, '0.0.0.0', () => {
    logger.info(`========================================`);
    logger.info(`SmartSafe WhatsApp Server running on port ${PORT}`);
    logger.info(`API: http://localhost:${PORT}`);
    logger.info(`Health: http://localhost:${PORT}/health`);
    logger.info(`========================================`);
});

// Graceful shutdown
process.on('SIGINT', async () => {
    logger.info('Shutting down...');
    for (const [account, sock] of sessions) {
        try {
            sock.end(undefined);
        } catch (e) { }
    }
    for (const [account, entry] of stores) {
        try {
            entry.persist();
        } catch (e) {
            logger.warn(`Failed to persist store for ${account} on shutdown`, e);
        }
    }
    persistMessages();
    process.exit(0);
});

module.exports = { app, sessions, messageStore, persistMessages, getMetrics, normalizeAccount };
