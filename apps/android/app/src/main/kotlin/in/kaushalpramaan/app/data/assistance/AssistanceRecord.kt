package `in`.kaushalpramaan.app.data.assistance

import androidx.room.*
import `in`.kaushalpramaan.app.data.draft.EvidenceDraftEntity
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "evidence_assistance", foreignKeys = [ForeignKey(
    entity = EvidenceDraftEntity::class, parentColumns = ["id"], childColumns = ["evidenceId"], onDelete = ForeignKey.CASCADE,
)], indices = [Index("assessmentId")])
data class AssistanceRecord(
    @PrimaryKey val evidenceId: String,
    val assessmentId: String,
    val taskId: String,
    val revisionNumber: Int,
    val generation: String,
    val inputPath: String,
    val inputSha256: String,
    val durationMs: Long?,
    val status: String,
    val stage: String,
    val resultJson: String?,
    val sealedSnapshotJson: String?,
    val errorCategory: String?,
)

@Dao
interface AssistanceDao {
    @Query("SELECT * FROM evidence_assistance WHERE assessmentId = :assessmentId")
    fun observe(assessmentId: String): Flow<List<AssistanceRecord>>

    @Query("SELECT * FROM evidence_assistance WHERE evidenceId = :evidenceId")
    suspend fun get(evidenceId: String): AssistanceRecord?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(record: AssistanceRecord)

    @Query("DELETE FROM evidence_assistance WHERE evidenceId = :evidenceId")
    suspend fun delete(evidenceId: String)
}
