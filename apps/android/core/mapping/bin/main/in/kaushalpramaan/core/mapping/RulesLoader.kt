package `in`.kaushalpramaan.core.mapping

import kotlinx.serialization.json.Json

private val json = Json { ignoreUnknownKeys = true }

/**
 * Loads the pinned CON/Q0602 pack data from classpath resources bundled by
 * build.gradle.kts's syncPackResources task (copied verbatim from
 * packs/ae-con-q0602 -- the single canonical source shared with
 * ml/mapping/matcher.py). Works both on the JVM (unit tests) and on-device
 * (the resources are packaged into the APK as merged Java resources).
 */
object RulesLoader {
    fun load(resourceLoader: (String) -> String = ::readClasspathResource): Rules {
        val links = json.decodeFromString(LinksFile.serializer(), resourceLoader("/pack/mapping/links.json"))
        val keywords = json.decodeFromString(KeywordsFile.serializer(), resourceLoader("/pack/mapping/keywords.json"))
        val thresholds = json.decodeFromString(ThresholdsFile.serializer(), resourceLoader("/pack/mapping/thresholds.json"))
        val tasksFile = json.decodeFromString(TasksFile.serializer(), resourceLoader("/pack/tasks.json"))
        val nosTask = tasksFile.tasks.associate { it.nos to it.id }
        return Rules(links = links, keywords = keywords, thresholds = thresholds, nosTask = nosTask, tasksFile = tasksFile)
    }
}

fun readClasspathResource(path: String): String {
    val stream = object {}.javaClass.getResourceAsStream(path)
        ?: throw IllegalStateException("missing bundled pack resource: $path (did syncPackResources run?)")
    return stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
}
