// whatsapp-server/worker.js - Buttons/List/Reaction + Queue
const { Worker } = require('bullmq');
const { createClient } = require('redis');

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const connection = createClient({ url: REDIS_URL });
connection.connect();

const worker = new Worker('whatsapp-messages', async (job) => {
    const { account, jid, msgOptions, messageId, reactionData } = job.data;

    const { sessions, messageStore, persistMessages, getMetrics } = require('./index.js');
    let sock = sessions.get(account);

    if (!sock || !sock.user) throw new Error('Account not connected');

    try {
        let sent;

        if (reactionData) {
            // Reaction
            sent = await sock.sendMessage(jid, {
                reaction: { text: reactionData.emoji, key: reactionData.originalKey }
            });
        } else {
            // Normal / buttons / list
            sent = await sock.sendMessage(jid, msgOptions);
        }

        const id = messageId || sent?.key?.id;
        messageStore.set(id, {
            id,
            to: jid.replace('@s.whatsapp.net', ''),
            content: msgOptions?.text || reactionData?.emoji || 'Interactive',
            status: 'sent',
            account,
            timestamp: Date.now()
        });
        persistMessages();

        const metrics = getMetrics(account);
        metrics.messages_sent += 1;
        metrics.last_sent_at = Date.now();

        console.log(`✅ QUEUE SUCCESS: ${jid} ${reactionData ? '(Reaction ' + reactionData.emoji + ')' : '(Interactive)'}`);
        return { success: true, messageId: id };
    } catch (err) {
        console.error(`❌ QUEUE FAILED: ${jid}`, err);
        throw err;
    }
}, {
    connection,
    concurrency: 8,
    limiter: { max: 40, duration: 60000 }
});

worker.on('completed', job => console.log(`Job ${job.id} completed`));
worker.on('failed', (job, err) => console.error(`Job ${job.id} failed:`, err.message));

console.log('🚀 WhatsApp Advanced Queue Worker Started (Buttons/List/Reaction)');

