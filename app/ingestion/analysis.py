from pydantic import BaseModel

from app.llm.client import generate_structured

ANALYSIS_PROMPT = """You are analyzing a transcript of a gospel sermon or spiritual message. \
Your job is to help someone who listened to this message recall and apply what was taught — \
without putting words in the preacher's mouth.

Produce a structured analysis with the following fields. Follow the grounding rules for each:

- summary: A concise, neutral paragraph (4-6 sentences) describing what the message covered. \
Describe what the preacher taught, not your own commentary on it.

- key_teachings: The major points and arguments the preacher actually made, in the order they \
build on each other. Each teaching should be traceable to something stated in the transcript — \
do not introduce teachings the transcript doesn't support, even if they'd fit the topic.

- themes: 3-6 short, reusable theme labels (1-3 words each, e.g. "faith", "God's provision", \
"perseverance") that this message would be filed under. These should be general enough to match \
other sermons on the same topic, not overly specific to this one message.

- bible_references: Every Bible passage the preacher explicitly cites or quotes, formatted as \
"Book Chapter:Verse" (e.g. "Romans 8:28") or a range (e.g. "Psalm 23:1-4"). Only include \
passages actually referenced in the transcript — do not add passages that would merely be \
thematically relevant.

- action_points: Practical, concrete actions a listener could take this week in response to the \
message. Unlike key_teachings, these MAY be your own synthesis of how to apply the message — \
but each one should clearly follow from something the sermon actually taught, not be generic \
spiritual advice unrelated to this specific message.

- reflection_questions: 3-5 open-ended questions that help a listener personally reflect on and \
apply the message. These are explicitly your own generated questions, meant to prompt the \
listener's own thinking — they do not need to have been asked in the sermon itself.

Transcript:
{transcript}
"""


class SermonAnalysisResult(BaseModel):
    summary: str
    key_teachings: list[str]
    themes: list[str]
    bible_references: list[str]
    action_points: list[str]
    reflection_questions: list[str]


class AnalysisParseError(Exception):
    pass


def analyze_transcript(transcript: str) -> SermonAnalysisResult:
    result = generate_structured(
        prompt=ANALYSIS_PROMPT.format(transcript=transcript),
        response_schema=SermonAnalysisResult,
    )
    if result is None:
        raise AnalysisParseError("LLM did not return a parseable structured response")
    return result
