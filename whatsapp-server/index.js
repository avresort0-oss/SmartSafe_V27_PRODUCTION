/**
 * SmartSafe V27 - WhatsApp Node.js Server
 * Built on Express + Baileys (WhiskeySockets)
 * Provides REST API for Python GUI with Queue + Interactive Messages
 */

const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const pino = require('pino');
const QRCode = require('qrcode');
const fs = require('fs-extra');
const path = require('path');
const pkg = require('./package.json');
const Agent = require('agentkeepalive');

const { Queue } = require('bullmq');
const { createClient } = require('redis');
const rateLimit = require('express-rate-limit');

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const redisConnection = createClient({ url: REDIS_URL });
redisConnection.connect().catch(console.error);

const messageQueue = new Queue('whatsapp-messages', {
    connection: redisConnection,
    defaultJobOptions: {
        attempts: 3,
        backoff: { type: 'exponential', delay: 2000 },
        removeOnComplete: true
    }
});

// Load environment variables from .env if present (project root preferred).
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
};

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

// POWERFUL /SEND (Text + Media + Buttons + List + Reaction + Queue)
app.post('/send', async (req, res) => {
    const {
        number,
        message,
        account,
        media_url,
        buttons,
        list,
        reaction,
        messageId
    } = req.body;

    if (!number) return res.json({ ok: false, error: 'Number required' });

    const accountName = normalizeAccount(account);
    const sock = sessions.get(accountName);
    if (!sock || !sock.user) {
        return res.json({ ok: false, error: 'Account not connected' });
    }

    const jid = number.includes('@') ? number : `${number}@s.whatsapp.net`;

    let msgOptions = {};
    let reactionData = null;

    // 1. Normal text + media
    if (message) msgOptions.text = message;
    if (media_url) {
        if (media_url.match(/\.(jpg|jpeg|png|gif|webp)$/i)) msgOptions.image = { url: media_url };
        else if (media_url.match(/\.(mp4|webm)$/i)) msgOptions.video = { url: media_url };
        else if (media_url.match(/\.(mp3|opus)$/i)) msgOptions.audio = { url: media_url };
        else msgOptions.document = { url: media_url };
    }

    // 2. Buttons
    if (buttons && Array.isArray(buttons) && buttons.length > 0) {
        msgOptions.buttons = buttons.map((btn, i) => ({
            buttonId: `btn_${i}`,
            buttonText: { displayText: btn.text || btn },
            type: 1
        }));
        msgOptions.footer = "SmartSafe V27 PRO";
        msgOptions.headerType = 1;
    }

    // 3. List (Interactive Menu)
    if (list && list.sections) {
        msgOptions.text = message || "Choose option:";
        msgOptions.sections = list.sections;
        msgOptions.buttonText = list.buttonText || "Select";
        msgOptions.listType = 1;
        msgOptions.footer = "SmartSafe V27 PRO";
    }

    // 4. Reaction
    if (reaction && reaction.emoji && reaction.originalMessageId) {
        reactionData = { emoji: reaction.emoji, originalKey: { id: reaction.originalMessageId, remoteJid: jid, fromMe: true } };
    }

    const jobId = messageId || `msg_${Date.now()}_${Math.random().toString(36).slice(2)}`;

    // Queue job
    await messageQueue.add('send', {
        account: accountName,
        jid,
        msgOptions: Object.keys(msgOptions).length ? msgOptions : { text: message || " " },
        messageId: jobId,
        reactionData
    }, { delay: Math.random() * 2000 + 1000 });

    res.json({
        ok: true,
        message: reactionData ? 'Reaction queued' : 'Message queued (buttons/list/media)',
        jobId,
        status: 'queued',
        type: reactionData ? 'reaction' : (buttons ? 'buttons' : list ? 'list' : 'text/media')
    });
});

// Send bulk messages (legacy + queued)
app.post('/send-bulk', async (req, res) => {
    const { numbers, message, account, media_url, buttons, list } = req.body;
    if (!Array.isArray(numbers) || numbers.length === 0) {
        return res.json({ ok: false, error: 'Numbers array required' });
    }

    const accountName = normalizeAccount(account);
    for (const num of numbers) {
        const jid = num.includes('@') ? num : `${num}@s.whatsapp.net`;
        const msgOptions = { text: message };
        if (media_url) {
            if (media_url.match(/\.(jpg|jpeg|png|gif|webp)$/i)) msgOptions.image = { url: media_url };
            else if (media_url.match(/\.(mp4|webm)$/i)) msgOptions.video = { url: media_url };
            else msgOptions.document = { url: media_url };
        }
        // buttons/list same as /send
        if (buttons) msgOptions.buttons = buttons.map((btn, i) => ({
            buttonId: `btn_${i}`,
            buttonText: { displayText: btn.text || btn },
            type: 1
        }));
        if (list && list.sections) {
            msgOptions.sections = list.sections;
            msgOptions.buttonText = list.buttonText || "Select";
            msgOptions.listType = 1;
        }

        await messageQueue.add('send', { account: accountName, jid, msgOptions });
    }

    res.json({ ok: true, queued: numbers.length, message: 'Bulk queued' });
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

// Export for worker.js
module.exports = { app, sessions, messageStore, persistMessages, getMetrics, normalizeAccount, messageQueue };

