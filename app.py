import os
import re
import shutil
import subprocess
from datetime import timedelta

import gradio as gr
import whisper


def format_ass_timestamp(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    centis = int(td.microseconds / 10000)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def format_srt_timestamp(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def hex_to_ass_color(hex_color: str, alpha: str = "00") -> str:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H{alpha}{b}{g}{r}"
    return f"&H{alpha}FFFFFF"


POSITION_ALIGNMENTS = {
    "Bottom Center": 2,
    "Middle / Center": 5,
    "Top Center": 8,
    "Bottom Left": 1,
    "Bottom Right": 3,
    "Top Left": 7,
    "Top Right": 9,
}


def process_video(
    video_path,
    custom_subtitle,
    model_size,
    words_per_caption,
    position,
    vertical_offset,
    font_family,
    font_size,
    is_bold,
    primary_color,
    bg_style,
    bg_padding,
    bg_color,
    bg_opacity,
    highlight_input,
    highlight_color,
    animation_style,
):
    if not video_path:
        return None, None, None, "Please upload a video."

    base_name = os.path.splitext(os.path.basename(video_path))[0]
    output_video = f"{base_name}_captioned.mp4"
    output_ass = f"{base_name}_subtitles.ass"
    output_srt = f"{base_name}_subtitles.srt"

    try:
        # PATH A: Direct .ASS File Upload
        if custom_subtitle is not None and custom_subtitle.name.lower().endswith(
            ".ass"
        ):
            yield None, None, None, "📝 Using uploaded .ass file directly..."
            shutil.copy(custom_subtitle.name, output_ass)
            # Cannot easily extract SRT from advanced ASS, skip SRT generation
            output_srt = None

        # PATH B & C: Generate ASS + SRT from Custom SRT or Whisper AI
        else:
            keywords = [
                k.strip().lower() for k in highlight_input.split(",") if k.strip()
            ]
            alignment = POSITION_ALIGNMENTS.get(position, 2)

            ass_primary = hex_to_ass_color(primary_color, alpha="00")
            ass_highlight = hex_to_ass_color(highlight_color, alpha="00")
            alpha_hex = f"{int((100 - bg_opacity) * 2.55):02X}"
            ass_bg = hex_to_ass_color(bg_color, alpha=alpha_hex)
            bold_val = -1 if is_bold else 0

            if bg_style == "Solid Box (Square)":
                ass_styles = f"Style: Text,{font_family},{font_size},{ass_primary},&H000000FF,{ass_bg},{ass_bg},{bold_val},0,0,0,100,100,0,0,3,{bg_padding},0,{alignment},20,20,{vertical_offset},1"
            elif bg_style == "Standard Outline":
                ass_styles = f"Style: Text,{font_family},{font_size},{ass_primary},&H000000FF,{ass_bg},{ass_bg},{bold_val},0,0,0,100,100,0,0,1,{bg_padding},0,{alignment},20,20,{vertical_offset},1"
            else:
                ass_styles = f"Style: Text,{font_family},{font_size},{ass_primary},&H000000FF,&H00000000,&H00000000,{bold_val},0,0,0,100,100,0,0,1,0,0,{alignment},20,20,{vertical_offset},1"

            ass_header = f"""[Script Info]
ScriptType: v4.00+
Collisions: Normal

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{ass_styles}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
            anim_tag = ""
            if animation_style == "Fade In / Out":
                anim_tag = r"{\fad(150,150)}"
            elif animation_style == "Pop / Zoom (Punchy)":
                anim_tag = r"{\fscx80\fscy80\t(0,70,\fscx110\fscy110)\t(70,130,\fscx100\fscy100)}"
            elif animation_style == "Blur Reveal":
                anim_tag = r"{\blur10\t(0,150,\blur0)}"
            elif animation_style == "Spring Up":
                anim_tag = r"{\fscy0\t(0,150,\fscy100)}"

            dialogue_lines_ass = []
            dialogue_lines_srt = []
            srt_index = 1

            def append_dialogue(start_sec, end_sec, chunk_words):
                nonlocal srt_index
                # Generate ASS formats
                start_ass = format_ass_timestamp(start_sec)
                end_ass = format_ass_timestamp(end_sec)

                # Generate SRT formats
                start_srt = format_srt_timestamp(start_sec)
                end_srt = format_srt_timestamp(end_sec)

                # Process ASS styled text
                formatted_words = []
                for w_text in chunk_words:
                    clean_w = re.sub(r"[^\w\s]", "", w_text).lower()
                    if clean_w in keywords:
                        formatted_words.append(
                            f"{{\\c{ass_highlight}}}{w_text}{{\\c{ass_primary}}}"
                        )
                    else:
                        formatted_words.append(w_text)

                line_text_ass = anim_tag + " ".join(formatted_words)
                dialogue_lines_ass.append(
                    f"Dialogue: 0,{start_ass},{end_ass},Text,,0,0,0,,{line_text_ass}\n"
                )

                # Process raw SRT text
                raw_text = " ".join([w.strip() for w in chunk_words])
                dialogue_lines_srt.append(
                    f"{srt_index}\n{start_srt} --> {end_srt}\n{raw_text}\n\n"
                )
                srt_index += 1

            # PATH B: Custom SRT
            if custom_subtitle is not None and custom_subtitle.name.lower().endswith(
                ".srt"
            ):
                yield None, None, None, "📝 Parsing custom SRT and applying styles..."
                with open(custom_subtitle.name, "r", encoding="utf-8") as f:
                    content = f.read()

                pattern = re.compile(
                    r"(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n(.*?)(?=\n\n|\n*$|\Z)",
                    re.DOTALL,
                )

                def srt_ts_to_seconds(ts):
                    h, m, s_ms = ts.split(":")
                    s, ms = s_ms.replace(".", ",").split(",")
                    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

                for match in pattern.finditer(content.strip()):
                    start_sec = srt_ts_to_seconds(match.group(2))
                    end_sec = srt_ts_to_seconds(match.group(3))
                    append_dialogue(
                        start_sec, end_sec, match.group(4).replace("\n", " ").split()
                    )

            # PATH C: Whisper AI
            else:
                yield None, None, None, "⏳ Transcribing audio on GTX 980 Ti..."
                model = whisper.load_model(model_size, device="cuda")
                result = model.transcribe(
                    video_path, language="it", word_timestamps=True
                )

                yield None, None, None, "📝 Formatting subtitle blocks..."
                for segment in result["segments"]:
                    words = segment.get("words", [])
                    if not words:
                        continue

                    for i in range(0, len(words), int(words_per_caption)):
                        chunk = words[i : i + int(words_per_caption)]
                        start_sec = chunk[0]["start"]
                        end_sec = chunk[-1]["end"]
                        append_dialogue(
                            start_sec, end_sec, [w["word"].strip() for w in chunk]
                        )

            # Write files
            with open(output_ass, "w", encoding="utf-8") as f:
                f.write(ass_header)
                f.writelines(dialogue_lines_ass)

            with open(output_srt, "w", encoding="utf-8") as f:
                f.writelines(dialogue_lines_srt)

        yield None, output_ass, output_srt, "🎨 Burning subtitles with FFmpeg..."

        escaped_ass = output_ass.replace("\\", "/").replace(":", "\\:")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vf",
            f"ass='{escaped_ass}'",
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-preset",
            "fast",
            "-c:a",
            "copy",
            output_video,
        ]

        subprocess.run(cmd, check=True)
        yield output_video, output_ass, output_srt, "✅ Complete! Video and subtitle tracks are ready."

    except Exception as e:
        yield None, None, None, f"❌ Error: {str(e)}"


# --- Gradio Interface ---
with gr.Blocks(title="AI Video Captioner") as app:
    gr.Markdown("# 🎬 AI Video Captioner")

    with gr.Row():
        with gr.Column():
            video_input = gr.Video(label="Upload Video (MP4)")
            custom_subtitle_input = gr.File(
                label="Optional: Upload Existing Subtitle (.srt or .ass)",
                file_types=[".srt", ".ass"],
            )

            with gr.Accordion(
                "Speech-to-Text Pacing (Ignored if file uploaded)", open=False
            ):
                model_dropdown = gr.Dropdown(
                    choices=["base", "small", "medium", "large"],
                    value="small",
                    label="Whisper Model",
                )
                words_per_caption = gr.Slider(
                    minimum=1,
                    maximum=8,
                    value=2,
                    step=1,
                    label="Words Per Caption Chunk",
                )

            gr.Markdown("### Placement & Layout")
            with gr.Row():
                position = gr.Dropdown(
                    choices=list(POSITION_ALIGNMENTS.keys()),
                    value="Bottom Center",
                    label="Screen Position",
                )
                vertical_offset = gr.Slider(
                    minimum=0,
                    maximum=300,
                    value=50,
                    step=5,
                    label="Vertical Margin / Y-Offset (px)",
                )

            gr.Markdown("### Typography")
            with gr.Row():
                font_family = gr.Dropdown(
                    choices=[
                        "Liberation Sans",
                        "DejaVu Sans",
                        "Liberation Serif",
                        "DejaVu Serif",
                        "Liberation Mono",
                    ],
                    value="Liberation Sans",
                    label="Built-in Font",
                )
                font_size = gr.Slider(
                    minimum=12, maximum=64, value=22, step=1, label="Font Size"
                )
                is_bold = gr.Checkbox(label="Bold", value=True)
            primary_color = gr.ColorPicker(value="#FFFFFF", label="Text Color")

            gr.Markdown("### Background Shape & Padding")
            bg_style = gr.Dropdown(
                choices=["Solid Box (Square)", "Standard Outline", "None"],
                value="Solid Box (Square)",
                label="Background Style",
            )
            with gr.Row():
                bg_padding = gr.Slider(
                    minimum=0,
                    maximum=30,
                    value=12,
                    step=1,
                    label="Internal Padding / Thickness",
                )
                bg_opacity = gr.Slider(
                    minimum=0, maximum=100, value=90, step=1, label="Opacity (%)"
                )
            bg_color = gr.ColorPicker(value="#000000", label="Background Color")

            gr.Markdown("### Highlights & Animation")
            with gr.Row():
                highlight_input = gr.Textbox(
                    placeholder="e.g. ciao, importante",
                    label="Keywords to Highlight (comma-separated)",
                )
                highlight_color = gr.ColorPicker(
                    value="#FFD700", label="Highlight Color"
                )
            animation_style = gr.Dropdown(
                choices=[
                    "Pop / Zoom (Punchy)",
                    "Fade In / Out",
                    "Blur Reveal",
                    "Spring Up",
                    "None",
                ],
                value="Pop / Zoom (Punchy)",
                label="Animation Preset",
            )

            submit_btn = gr.Button("Generate Captioned Video", variant="primary")

        with gr.Column():
            video_output = gr.Video(label="Processed Video")
            with gr.Row():
                ass_output = gr.File(label="Export .ass (Styled Subtitles)")
                srt_output = gr.File(label="Export .srt (Raw Subtitles)")
            status_output = gr.Textbox(label="Status", interactive=False)

    submit_btn.click(
        fn=process_video,
        inputs=[
            video_input,
            custom_subtitle_input,
            model_dropdown,
            words_per_caption,
            position,
            vertical_offset,
            font_family,
            font_size,
            is_bold,
            primary_color,
            bg_style,
            bg_padding,
            bg_color,
            bg_opacity,
            highlight_input,
            highlight_color,
            animation_style,
        ],
        outputs=[video_output, ass_output, srt_output, status_output],
    )

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)
