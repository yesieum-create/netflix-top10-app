package com.sisa.top10

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

// ───────── 데이터 형식 (server/pipeline.py 가 만드는 top10.json 과 1:1) ─────────

@Serializable
data class Top10Data(
    val generated_at: String,
    val source_note: String = "",
    val country: Ranking,
    val global: Ranking,
    val trending: Ranking? = null,
    val daily: DailyRanking? = null,
    val titles: Map<String, Title> = emptyMap(),
)

@Serializable
data class Ranking(val code: String? = null, val week: String, val items: List<RankItem>)

@Serializable
data class DailyRanking(val date: String, val items: List<RankItem>)

@Serializable
data class RankItem(
    val id: String,
    val rank: Int,
    val category: String? = null,
    val type: String,
    val weeks_in_top10: Int? = null,
    val weekly_views: Long? = null,
    val rank_change: Int? = null,
    val is_new: Boolean = false,
)

@Serializable
data class Title(
    val id: String,
    val show_title: String,
    val season_title: String? = null,
    val type: String,
    val title_ko: String? = null,
    val year: String? = null,
    val genres: List<String>? = null,
    val cast: List<String>? = null,
    val poster: String? = null,
    val backdrop: String? = null,
    val vote: Double? = null,
    val ai: AiNote? = null,
) {
    val displayName: String get() = title_ko ?: show_title
}

@Serializable
data class AiNote(
    val synopsis_ko: String,
    val watch_points: List<String>,
    val recommend_reason: String,
    val recommend_for: List<String> = emptyList(),
    val mood_tags: List<String> = emptyList(),
    val confidence: String = "high",
)

// ───────── 저장소: 서버 JSON 다운로드 + 오프라인 캐시 ─────────

class Top10Repository(private val cacheDir: File) {
    private val http = OkHttpClient.Builder().callTimeout(20, TimeUnit.SECONDS).build()
    private val json = Json { ignoreUnknownKeys = true; coerceInputValues = true }
    private val cacheFile get() = File(cacheDir, "top10.json")

    /** 서버에서 최신 데이터를 받고, 실패하면 마지막으로 저장한 데이터를 보여준다. (데이터, 오프라인여부) */
    suspend fun load(): Pair<Top10Data, Boolean> = withContext(Dispatchers.IO) {
        try {
            val body = http.newCall(Request.Builder().url(BuildConfig.DATA_URL).build()).execute().use {
                check(it.isSuccessful) { "HTTP ${it.code}" }
                it.body!!.string()
            }
            val data = json.decodeFromString<Top10Data>(body)
            cacheFile.writeText(body)
            data to false
        } catch (e: Exception) {
            if (cacheFile.exists()) json.decodeFromString<Top10Data>(cacheFile.readText()) to true
            else throw e
        }
    }
}

// ───────── 화면 상태 ─────────

sealed interface UiState {
    data object Loading : UiState
    data class Ready(val data: Top10Data, val offline: Boolean) : UiState
    data class Error(val message: String) : UiState
}

class Top10ViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = Top10Repository(app.cacheDir)
    private val _state = MutableStateFlow<UiState>(UiState.Loading)
    val state: StateFlow<UiState> = _state

    init { refresh() }

    fun refresh() = viewModelScope.launch {
        if (_state.value !is UiState.Ready) _state.value = UiState.Loading
        _state.value = try {
            val (d, offline) = repo.load()
            UiState.Ready(d, offline)
        } catch (e: Exception) {
            UiState.Error("데이터를 불러오지 못했습니다. 인터넷 연결을 확인해 주세요.\n(${e.message})")
        }
    }

    fun title(id: String): Title? = (state.value as? UiState.Ready)?.data?.titles?.get(id)
}
