package com.sisa.top10

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage

// ═══════════════════════════ 홈: 순위 목록 ═══════════════════════════

private enum class Tab(val label: String) { KR("한국 주간"), GLOBAL("글로벌 주간"), TREND("급상승") }
private enum class Kind(val label: String) { ALL("전체"), MOVIE("영화"), TV("시리즈") }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(vm: Top10ViewModel, onOpen: (String) -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableStateOf(Tab.KR) }
    var kind by rememberSaveable { mutableStateOf(Kind.ALL) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("넷플 TOP10 가이드", fontWeight = FontWeight.Bold) },
                actions = { IconButton(onClick = { vm.refresh() }) { Icon(Icons.Default.Refresh, "새로고침") } },
            )
        }
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            TabRow(selectedTabIndex = tab.ordinal) {
                Tab.entries.forEach { t ->
                    Tab(selected = tab == t, onClick = { tab = t }, text = { Text(t.label) })
                }
            }
            Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Kind.entries.forEach { k ->
                    FilterChip(selected = kind == k, onClick = { kind = k }, label = { Text(k.label) })
                }
            }
            when (val s = state) {
                UiState.Loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
                is UiState.Error -> Box(Modifier.fillMaxSize().padding(24.dp), Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(s.message)
                        Spacer(Modifier.height(12.dp))
                        Button(onClick = { vm.refresh() }) { Text("다시 시도") }
                    }
                }
                is UiState.Ready -> RankList(s, tab, kind, onOpen)
            }
        }
    }
}

@Composable
private fun RankList(s: UiState.Ready, tab: Tab, kind: Kind, onOpen: (String) -> Unit) {
    val d = s.data
    val (header, items) = when (tab) {
        Tab.KR -> "Netflix 공식 한국 TOP10 · ${d.country.week} 주" to d.country.items
        Tab.GLOBAL -> "Netflix 공식 글로벌 TOP10 · ${d.global.week} 주" to d.global.items
        Tab.TREND -> "이번 주 신규 진입 · 순위 상승 (한국, ${d.trending?.week ?: d.country.week} 주)" to
            (d.trending?.items ?: emptyList())
    }
    val filtered = items.filter {
        when (kind) { Kind.ALL -> true; Kind.MOVIE -> it.type == "movie"; Kind.TV -> it.type == "tv" }
    }

    LazyColumn(contentPadding = PaddingValues(bottom = 24.dp)) {
        item {
            if (s.offline) Text(
                "오프라인 — 마지막으로 받은 데이터를 보여드립니다",
                color = MaterialTheme.colorScheme.error, fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
            if (header.isNotEmpty()) Text(
                header, style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
            )
        }
        if (filtered.isEmpty()) item {
            Text(
                if (tab == Tab.TREND) "이번 주는 새로 들어오거나 크게 오른 작품이 없습니다." else "표시할 작품이 없습니다.",
                modifier = Modifier.padding(24.dp)
            )
        }
        items(filtered, key = { "${it.category}-${it.rank}-${it.id}" }) { r ->
            val t = d.titles[r.id]
            RankRow(r, t) { onOpen(r.id) }
        }
        item {
            Text(
                d.source_note + "\n본 앱은 TMDB API를 사용하지만 TMDB의 보증·인증을 받지 않았습니다. " +
                    "Netflix와 무관한 비공식 서비스입니다.",
                fontSize = 11.sp, color = MaterialTheme.colorScheme.outline,
                modifier = Modifier.padding(16.dp)
            )
        }
    }
}

@Composable
private fun RankRow(r: RankItem, t: Title?, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            "${r.rank}", fontSize = 32.sp, fontWeight = FontWeight.Black,
            color = MaterialTheme.colorScheme.primary, modifier = Modifier.width(44.dp)
        )
        AsyncImage(
            model = t?.poster, contentDescription = null, contentScale = ContentScale.Crop,
            modifier = Modifier.size(60.dp, 88.dp).clip(RoundedCornerShape(6.dp))
        )
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                t?.displayName ?: r.id.substringBefore("||"),
                fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis
            )
            t?.season_title?.let { Text(it, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis) }
            val meta = buildList {
                if (r.is_new) add("NEW")
                add(if (r.type == "tv") "시리즈" else "영화")
                r.weeks_in_top10?.let { add("${it}주째 TOP10") }
                r.weekly_views?.let { add("주간 ${formatViews(it)}회") }
                r.rank_change?.let { if (it > 0) add("▲$it") else if (it < 0) add("▼${-it}") }
            }.joinToString(" · ")
            Text(meta, fontSize = 12.sp, color = MaterialTheme.colorScheme.outline)
            t?.ai?.recommend_reason?.let {
                Text(it, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

private fun formatViews(v: Long): String = when {
    v >= 100_000_000 -> "%.1f억".format(v / 100_000_000.0)
    v >= 10_000 -> "%,d만".format(v / 10_000)
    else -> "%,d".format(v)
}

// ═══════════════════════════ 상세: AI 해설 ═══════════════════════════

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun DetailScreen(t: Title?, onBack: () -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(t?.displayName ?: "", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "뒤로") }
                }
            )
        }
    ) { pad ->
        if (t == null) {
            Box(Modifier.padding(pad).fillMaxSize(), Alignment.Center) { Text("작품 정보를 찾을 수 없습니다.") }
            return@Scaffold
        }
        Column(Modifier.padding(pad).verticalScroll(rememberScrollState())) {
            AsyncImage(
                model = t.backdrop ?: t.poster, contentDescription = null, contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f)
            )
            Column(Modifier.padding(16.dp)) {
                Text(t.displayName, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                if (t.title_ko != null && t.title_ko != t.show_title) Text(t.show_title, color = MaterialTheme.colorScheme.outline)
                val meta = listOfNotNull(
                    t.year?.takeIf { it.isNotBlank() },
                    if (t.type == "tv") "시리즈" else "영화",
                    t.genres?.takeIf { it.isNotEmpty() }?.joinToString(", "),
                    t.vote?.takeIf { it > 0 }?.let { "TMDB ★%.1f".format(it) },
                ).joinToString(" · ")
                Text(meta, fontSize = 13.sp)
                t.cast?.takeIf { it.isNotEmpty() }?.let { Text("출연 ${it.joinToString(", ")}", fontSize = 13.sp) }

                val ai = t.ai
                if (ai == null) {
                    Spacer(Modifier.height(24.dp))
                    Text("AI 해설을 준비 중입니다.")
                    return@Column
                }
                Section("줄거리") { Text(ai.synopsis_ko, lineHeight = 22.sp) }
                Section("감상 포인트 (스포일러 없음)") {
                    ai.watch_points.forEach { Text("• $it", lineHeight = 22.sp, modifier = Modifier.padding(bottom = 4.dp)) }
                }
                Section("이런 분께 추천") {
                    Text(ai.recommend_reason, lineHeight = 22.sp)
                    Spacer(Modifier.height(8.dp))
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        (ai.recommend_for + ai.mood_tags).forEach { AssistChip(onClick = {}, label = { Text(it) }) }
                    }
                }
                Spacer(Modifier.height(20.dp))
                Text(
                    "AI가 공개 정보를 바탕으로 작성한 소개입니다. 실제 내용과 다를 수 있습니다." +
                        if (ai.confidence == "low") "\n※ 이 작품은 참고 자료가 적어 소개가 간략합니다." else "",
                    fontSize = 11.sp, color = MaterialTheme.colorScheme.outline
                )
            }
        }
    }
}

@Composable
private fun Section(title: String, content: @Composable ColumnScope.() -> Unit) {
    Spacer(Modifier.height(20.dp))
    Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold,
        color = MaterialTheme.colorScheme.primary)
    Spacer(Modifier.height(6.dp))
    Column(content = content)
}
