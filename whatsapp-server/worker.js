// whatsapp-server/worker.js
const { Worker } = require('bullmq');
const { createClient } = require('redis');
const fs = require('fs-extra');
const path = require('path');

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';

const connection = createClient({ url: REDIS_URL });
connection.connect();

const worker = new Worker('whatsapp-messages', async (job) => {
    const { account, jid, msgOptions, messageId } = job.data;

    // Get shared state from index.js
    const { sessions, messageStore, persistMessages, getMetrics } = require('./index.js');
    let sock = sessions.get(account);

    if (!sock || !sock.user) {
        throw new Error('Account not connected');
    }

    try {
        const sent = await sock.sendMessage(jid, msgOptions);

        // Update store
        messageStore.set(messageId || sent.key.id, {
            id: sent.key.id,
            to: jid.replace('@s.whatsapp.net', ''),
            content: msgOptions.text || 'Media',
            status: 'sent',
            account,
            timestamp: Date.now()
        });
        persistMessages();

        // Update metrics
        const metrics = getMetrics(account);
        metrics.messages_sent += 1;
        metrics.last_sent_at = Date.now();

        console.log(`✅ QUEUE SUCCESS: ${jid}`);
        return { success: true, messageId: sent.key.id };
    } catch (err) {
        console.error(`❌ QUEUE FAILED: ${jid}`, err);
        throw err; // BullMQ will retry
    }
}, {
    connection,
    concurrency: 5,
    limiter: { max: 30, duration: 60000 }
});

worker.on('completed', job => console.log(`Job ${job.id} completed`));
worker.on('failed', (job, err) => console.error(`Job ${job.id} failed:`, err.message));

console.log('🚀 WhatsApp Queue Worker Started');
