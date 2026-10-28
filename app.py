
import re
from collections import Counter
from urllib.parse import urlparse, parse_qs

import streamlit as st
import matplotlib.pyplot as plt
from wordcloud import WordCloud
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# -------------------------------
# 1. 웹사이트 기본 설정
# -------------------------------
st.set_page_config(
    page_title="소비자 반응 비교 분석기",
    page_icon="📊",
    layout="wide"
)

st.title("📊 소비자 반응 비교 분석기")
st.write(
    "유튜브 영상 주소 2개를 입력하면 "
    "영상 정보와 댓글 반응을 비교해 줍니다."
)


# -------------------------------
# 2. 분석에 사용할 단어
# -------------------------------
POSITIVE_WORDS = [
    "좋다", "좋아요", "만족", "최고", "추천",
    "예쁘다", "편하다", "훌륭", "기대", "장점"
]

NEGATIVE_WORDS = [
    "비싸다", "비싸", "아쉽다", "별로", "불편",
    "실망", "문제", "불만", "최악", "단점"
]

STOPWORDS = {
    "정말", "너무", "진짜", "그냥", "영상",
    "오늘", "이거", "저거", "때문", "정도",
    "그리고", "하지만", "저는", "제가", "이런"
}


# -------------------------------
# 3. 유튜브 주소에서 영상 ID 추출
# -------------------------------
def get_video_id(url):
    url = url.strip()

    if not url.startswith(("https://", "http://")):
        url = "https://" + url

    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")

    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]

    elif host == "youtube.com" or host.endswith(".youtube.com"):
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] in ["shorts", "live", "embed"]:
                video_id = parts[1]
            else:
                video_id = ""

    else:
        video_id = ""

    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("유효한 유튜브 영상 주소를 입력해 주세요.")

    return video_id


# -------------------------------
# 4. 영상 정보와 댓글 가져오기
# -------------------------------
def fetch_video(youtube, video_id):
    video_response = youtube.videos().list(
        part="snippet,statistics",
        id=video_id
    ).execute()

    if not video_response.get("items"):
        raise ValueError("영상을 찾을 수 없습니다.")

    video = video_response["items"][0]
    stats = video["statistics"]

    info = {
        "title": video["snippet"]["title"],
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comment_count": int(stats.get("commentCount", 0))
    }

    comments = []
    page_token = None

    # 최대 500개의 최상위 댓글 수집
    for _ in range(5):
        response = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            pageToken=page_token,
            textFormat="plainText",
            order="relevance"
        ).execute()

        for item in response.get("items", []):
            snippet = item["snippet"]["topLevelComment"]["snippet"]

            comments.append({
                "text": snippet.get("textDisplay", ""),
                "likes": int(snippet.get("likeCount", 0)),
                "author": snippet.get("authorDisplayName", "익명"),
                "time": snippet.get("publishedAt", "")
            })

        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return info, comments


# -------------------------------
# 5. 댓글에서 단어 빈도 계산
# -------------------------------
def get_word_frequency(comments):
    text = " ".join(comment["text"] for comment in comments).lower()

    # 한글, 영문, 숫자로 된 단어 추출
    tokens = re.findall(r"[가-힣a-zA-Z0-9]+", text)

    # 두 글자 이상이고 제외 단어가 아닌 것만 사용
    words = [
        word for word in tokens
        if len(word) >= 2 and word not in STOPWORDS
    ]

    return Counter(words)


# -------------------------------
# 6. 워드클라우드 생성
# -------------------------------
def make_wordcloud(frequencies):
    if not frequencies:
        return None

    font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"

    cloud = WordCloud(
        font_path=font_path,
        width=800,
        height=450,
        background_color="white"
    ).generate_from_frequencies(dict(frequencies))

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(cloud, interpolation="bilinear")
    ax.axis("off")
    fig.tight_layout()

    return fig


# -------------------------------
# 7. 긍정·부정 키워드 계산
# -------------------------------
def count_sentiment_keywords(comments):
    text = " ".join(comment["text"] for comment in comments).lower()

    positive = sum(text.count(word) for word in POSITIVE_WORDS)
    negative = sum(text.count(word) for word in NEGATIVE_WORDS)

    return positive, negative


# -------------------------------
# 8. 주소 입력 화면
# -------------------------------
with st.form("video_form"):
    st.subheader("비교할 영상 주소 입력")

    url1 = st.text_input(
        "첫 번째 유튜브 영상",
        placeholder="https://www.youtube.com/watch?v=..."
    )

    url2 = st.text_input(
        "두 번째 유튜브 영상",
        placeholder="https://www.youtube.com/watch?v=..."
    )

    submitted = st.form_submit_button(
        "두 영상 비교 분석하기",
        use_container_width=True
    )


# -------------------------------
# 9. 분석 실행
# -------------------------------
if submitted:
    if not url1.strip() or not url2.strip():
        st.warning("유튜브 영상 주소 2개를 모두 입력해 주세요.")
        st.stop()

    try:
        video_id1 = get_video_id(url1)
        video_id2 = get_video_id(url2)

        if video_id1 == video_id2:
            st.warning("서로 다른 영상 주소 2개를 입력해 주세요.")
            st.stop()

        api_key = st.secrets["YOUTUBE_API_KEY"]
        youtube = build("youtube", "v3", developerKey=api_key)

        with st.spinner("영상과 댓글을 분석하고 있습니다..."):
            info1, comments1 = fetch_video(youtube, video_id1)
            info2, comments2 = fetch_video(youtube, video_id2)

        st.success("분석이 완료되었습니다!")

        # 영상 제목
        st.header("분석 대상 영상")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("영상 1")
            st.write(info1["title"])

        with col2:
            st.subheader("영상 2")
            st.write(info2["title"])

        # 통계 비교
        st.header("1. 영상 통계 비교")

        for label, key in [
            ("조회 수", "views"),
            ("좋아요 수", "likes"),
            ("댓글 수", "comment_count")
        ]:
            st.subheader(label)

            col1, col2 = st.columns(2)

            col1.metric("영상 1", f'{info1[key]:,}개' if key != "views" else f'{info1[key]:,}회')
            col2.metric("영상 2", f'{info2[key]:,}개' if key != "views" else f'{info2[key]:,}회')

        st.caption(
            f"실제로 분석한 최상위 댓글: "
            f"영상 1 {len(comments1):,}개 · "
            f"영상 2 {len(comments2):,}개"
        )

        # 워드클라우드
        st.header("2. 댓글 워드클라우드")

        freq1 = get_word_frequency(comments1)
        freq2 = get_word_frequency(comments2)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("영상 1")
            fig = make_wordcloud(freq1)
            if fig is not None:
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.info("표시할 단어가 없습니다.")

        with col2:
            st.subheader("영상 2")
            fig = make_wordcloud(freq2)
            if fig is not None:
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.info("표시할 단어가 없습니다.")

        # 좋아요 TOP 5
        st.header("3. 좋아요가 많은 댓글 TOP 5")

        col1, col2 = st.columns(2)

        for column, comments, title in [
            (col1, comments1, "영상 1"),
            (col2, comments2, "영상 2")
        ]:
            with column:
                st.subheader(title)

                top_comments = sorted(
                    comments,
                    key=lambda comment: comment["likes"],
                    reverse=True
                )[:5]

                if not top_comments:
                    st.info("확인 가능한 댓글이 없습니다.")

                for rank, comment in enumerate(top_comments, start=1):
                    st.markdown(
                        f"**{rank}위 · 좋아요 {comment['likes']:,}개**"
                    )
                    st.write(comment["text"])
                    st.caption(
                        f"작성자: {comment['author']} · "
                        f"작성 시각: {comment['time']}"
                    )
                    st.divider()

        # 긍정·부정 키워드
        st.header("4. 긍정·부정 키워드 비교")

        positive1, negative1 = count_sentiment_keywords(comments1)
        positive2, negative2 = count_sentiment_keywords(comments2)

        st.caption(
            "미리 정한 단어의 등장 횟수입니다. "
            "문맥을 이해하는 정밀한 감정 분석은 아닙니다."
        )

        st.dataframe(
            {
                "항목": ["긍정 키워드", "부정 키워드"],
                "영상 1": [positive1, negative1],
                "영상 2": [positive2, negative2]
            },
            use_container_width=True,
            hide_index=True
        )

        # 자주 등장한 단어 TOP 10
        st.header("5. 자주 등장한 단어 TOP 10")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("영상 1")
            st.dataframe(
                [
                    {"단어": word, "등장 횟수": count}
                    for word, count in freq1.most_common(10)
                ],
                use_container_width=True,
                hide_index=True
            )

        with col2:
            st.subheader("영상 2")
            st.dataframe(
                [
                    {"단어": word, "등장 횟수": count}
                    for word, count in freq2.most_common(10)
                ],
                use_container_width=True,
                hide_index=True
            )

    except KeyError:
        st.error(
            "API 키를 찾지 못했습니다. "
            "Streamlit Cloud의 Secrets에 "
            "YOUTUBE_API_KEY를 등록했는지 확인해 주세요."
        )

    except ValueError as error:
        st.error(str(error))

    except HttpError as error:
        st.error(
            "유튜브 API 요청에 실패했습니다. "
            "영상 주소, 댓글 공개 여부, API 키 및 "
            "API 활성화 상태를 확인해 주세요."
        )
        st.caption(str(error))

    except Exception as error:
        st.error(f"오류가 발생했습니다: {error}")
