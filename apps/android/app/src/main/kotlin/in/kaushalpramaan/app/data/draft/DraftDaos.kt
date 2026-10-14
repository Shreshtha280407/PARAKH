package `in`.kaushalpramaan.app.data.draft

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface AssessmentDraftDao {
    @Insert
    suspend fun insert(entity: AssessmentDraftEntity)

    @Update
    suspend fun update(entity: AssessmentDraftEntity)

    @Query("SELECT * FROM assessment_drafts WHERE state = 'ACTIVE' ORDER BY updated_at_millis DESC LIMIT 1")
    fun observeActive(): Flow<AssessmentDraftEntity?>

    @Query("SELECT * FROM assessment_drafts WHERE state = 'ACTIVE' ORDER BY updated_at_millis DESC LIMIT 1")
    suspend fun getActiveOnce(): AssessmentDraftEntity?

    @Query("SELECT * FROM assessment_drafts WHERE id = :id")
    suspend fun getById(id: String): AssessmentDraftEntity?

    @Query("UPDATE assessment_drafts SET state = 'DELETED', updated_at_millis = :nowMillis WHERE id = :id")
    suspend fun markDeleted(id: String, nowMillis: Long)

    @Query("SELECT * FROM assessment_drafts WHERE state = 'DELETED'")
    suspend fun listDeleted(): List<AssessmentDraftEntity>

    @Delete
    suspend fun hardDelete(entity: AssessmentDraftEntity)
}

@Dao
interface TaskDraftDao {
    @Insert
    suspend fun insertAll(entities: List<TaskDraftEntity>)

    @Update
    suspend fun update(entity: TaskDraftEntity)

    @Query("SELECT * FROM task_drafts WHERE assessmentId = :assessmentId ORDER BY taskId")
    fun observeForAssessment(assessmentId: String): Flow<List<TaskDraftEntity>>

    @Query("SELECT * FROM task_drafts WHERE assessmentId = :assessmentId AND taskId = :taskId")
    suspend fun getOne(assessmentId: String, taskId: String): TaskDraftEntity?

    @Query("SELECT * FROM task_drafts WHERE assessmentId = :assessmentId ORDER BY taskId")
    suspend fun getAllOnce(assessmentId: String): List<TaskDraftEntity>

    @Query("DELETE FROM task_drafts WHERE assessmentId = :assessmentId")
    suspend fun hardDeleteAllForAssessment(assessmentId: String)
}

@Dao
interface EvidenceDraftDao {
    @Insert
    suspend fun insert(entity: EvidenceDraftEntity)

    @Update
    suspend fun update(entity: EvidenceDraftEntity)

    @Query("SELECT * FROM evidence_drafts WHERE assessmentId = :assessmentId AND taskId = :taskId AND state != 'DELETED' ORDER BY created_at_millis")
    fun observeForTask(assessmentId: String, taskId: String): Flow<List<EvidenceDraftEntity>>

    @Query("SELECT * FROM evidence_drafts WHERE assessmentId = :assessmentId AND state != 'DELETED'")
    suspend fun getAllForAssessmentOnce(assessmentId: String): List<EvidenceDraftEntity>

    @Query("SELECT * FROM evidence_drafts WHERE assessmentId = :assessmentId AND taskId = :taskId AND state != 'DELETED'")
    suspend fun getAllForTaskOnce(assessmentId: String, taskId: String): List<EvidenceDraftEntity>

    @Query("SELECT * FROM evidence_drafts WHERE id = :id")
    suspend fun getById(id: String): EvidenceDraftEntity?

    @Query("SELECT * FROM evidence_drafts WHERE state = 'STAGING'")
    suspend fun listStaging(): List<EvidenceDraftEntity>

    @Query("SELECT * FROM evidence_drafts WHERE state = 'DELETED'")
    suspend fun listDeleted(): List<EvidenceDraftEntity>

    @Query("UPDATE evidence_drafts SET state = 'DELETED' WHERE id = :id")
    suspend fun markDeleted(id: String)

    @Delete
    suspend fun hardDelete(entity: EvidenceDraftEntity)

    @Query("DELETE FROM evidence_drafts WHERE assessmentId = :assessmentId")
    suspend fun hardDeleteAllForAssessment(assessmentId: String)
}

@Dao
interface OutboxDao {
    @Insert
    suspend fun insertAll(entities: List<OutboxItemEntity>)

    @Update
    suspend fun update(entity: OutboxItemEntity)

    @Query("SELECT * FROM outbox_items WHERE assessmentId = :assessmentId ORDER BY priority, created_at_millis")
    fun observeForAssessment(assessmentId: String): Flow<List<OutboxItemEntity>>

    @Query("SELECT * FROM outbox_items WHERE assessmentId = :assessmentId ORDER BY priority, created_at_millis")
    suspend fun getAllForAssessmentOnce(assessmentId: String): List<OutboxItemEntity>

    @Query("SELECT * FROM outbox_items WHERE id = :id")
    suspend fun getById(id: String): OutboxItemEntity?

    @Query("DELETE FROM outbox_items WHERE id = :id")
    suspend fun deleteById(id: String)

    @Query("DELETE FROM outbox_items WHERE assessmentId = :assessmentId")
    suspend fun deleteAllForAssessment(assessmentId: String)
}
