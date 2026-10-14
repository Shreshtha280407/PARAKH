package `in`.kaushalpramaan.app.data.sync

import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient

/** One shared OkHttpClient for every sync request -- real connection pooling/keep-alive across
 * chunk PUTs, which matters for upload throughput over a real (possibly poor) network. No
 * logging interceptor: the worker capability token travels in a header on every request, and
 * P6 security rule 8 forbids a secret ever reaching a log line, so there is deliberately no
 * generic HTTP logging path that could be mis-configured into capturing it later. */
object SyncHttpClient {
    val json: Json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(false) // SyncRepository's own retry/backoff loop owns this decision
            .build()
    }
}
