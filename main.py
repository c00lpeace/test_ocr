import gradio as gr
import json
from pathlib import Path
import base64
from PIL import Image
import io
from datetime import datetime
import httpx
import tempfile
import shutil
from typing import List, Tuple, Optional
import threading
import time

# ============================================================================
# 🎨 글로벌 상태 및 유틸리티
# ============================================================================

# 임시 파일 저장 경로
TEMP_DIR = Path(tempfile.gettempdir()) / "gradio_ocr"
TEMP_DIR.mkdir(exist_ok=True)

# 각 패널의 처리 결과 저장
panel_results = {
    1: {"images": [], "texts": [], "metadata": []},
    2: {"images": [], "texts": [], "metadata": []},
    3: {"images": [], "texts": [], "metadata": []}
}

# ============================================================================
# 🔧 vLLM API 및 이미지 처리 함수
# ============================================================================

def call_vllm_api(image_base64: str, prompt: str) -> Tuple[str, str]:
    """
    vLLM API를 호출하는 더미 함수 (실제 LLM은 미설정)
    Returns: (output_text, error_msg)
    """
    try:
        # 더미 응답 생성 (실제 환경에서는 vLLM API 호출)
        time.sleep(0.5)  # API 호출 시뮬레이션

        # 이미지 크기 기반 더미 텍스트 생성
        img_size = len(image_base64)

        if "Extract all text" in prompt and "exactly" in prompt:
            # OCR_PURE 모드
            output_text = f"[DEMO] Extracted Text from Image\n\nSample Product Name\nModel: ABC-123\nPrice: $99.99\n\n(Image size: {img_size//1000}KB)"
        elif "markdown" in prompt.lower():
            # OCR_MD 모드
            output_text = f"# Sample Product\n\n## Details\n- **Model**: ABC-123\n- **Price**: $99.99\n- **Features**: Feature 1, Feature 2\n\n(Image size: {img_size//1000}KB)"
        else:
            # OCR_DESC 또는 CUSTOM 모드
            output_text = f"# OCR Extraction Report\n\n## Image Overview\n- Product type: Sample Product\n- Colors: Multiple\n\n## Detected Text\nSample text from image\n\n(Image size: {img_size//1000}KB)"

        return output_text, ""
    except Exception as e:
        return "", f"Error: {str(e)}"


def image_to_base64(image_path: str) -> str:
    """이미지를 base64로 인코딩"""
    try:
        with Image.open(image_path) as img:
            # RGB로 변환 (RGBA 등 처리)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            buffered = io.BytesIO()
            img.save(buffered, format="JPEG")
            img_bytes = buffered.getvalue()
            return base64.b64encode(img_bytes).decode('utf-8')
    except Exception as e:
        raise Exception(f"Base64 인코딩 실패: {str(e)}")


def crop_image(image_path: str, crop_height: int, overlap: int) -> List[str]:
    """
    긴 이미지를 crop_height로 분할 (overlap 적용)
    Returns: 크롭된 이미지 경로 리스트
    """
    try:
        img = Image.open(image_path)
        width, height = img.size

        # 이미지가 crop_height보다 작으면 원본 반환
        if height <= crop_height:
            return [image_path]

        # 크롭 실행
        cropped_paths = []
        y = 0
        chunk_idx = 0

        while y < height:
            # 크롭 영역 계산
            bottom = min(y + crop_height, height)
            box = (0, y, width, bottom)

            # 크롭 및 저장
            cropped = img.crop(box)
            crop_path = TEMP_DIR / f"{Path(image_path).stem}_chunk{chunk_idx}{Path(image_path).suffix}"
            cropped.save(crop_path)
            cropped_paths.append(str(crop_path))

            # 다음 위치 계산 (overlap 적용)
            y += crop_height - overlap
            chunk_idx += 1

            # 무한 루프 방지
            if chunk_idx > 100:
                break

        return cropped_paths
    except Exception as e:
        raise Exception(f"이미지 크롭 실패: {str(e)}")


def download_image_from_url(url: str) -> Optional[str]:
    """
    URL에서 이미지 다운로드
    Returns: 다운로드된 이미지 경로 또는 None
    """
    try:
        response = httpx.get(url, timeout=10.0, follow_redirects=True)
        response.raise_for_status()

        # 이미지 저장
        img_name = f"downloaded_{int(time.time())}_{hash(url) % 10000}.jpg"
        img_path = TEMP_DIR / img_name

        with open(img_path, 'wb') as f:
            f.write(response.content)

        return str(img_path)
    except Exception as e:
        print(f"URL 다운로드 실패 ({url}): {str(e)}")
        return None


def load_prompt_template(mode: str, custom_prompt: str = "") -> str:
    """모드에 따라 프롬프트 로드"""
    if mode == "CUSTOM":
        return custom_prompt if custom_prompt.strip() else "Describe this image."
    elif mode == "OCR_PURE":
        return "Extract all text from this image exactly as shown."
    elif mode == "OCR_MD":
        return "Extract all text from this image and format it as markdown."
    elif mode == "OCR_DESC":
        # prompts/custom_ocr_1.md 파일 로드
        try:
            prompt_file = Path(__file__).parent / "prompts" / "custom_ocr_1.md"
            if prompt_file.exists():
                return prompt_file.read_text(encoding='utf-8')
            else:
                return "Extract and describe all text and visual elements from this image in markdown format."
        except:
            return "Extract and describe all text and visual elements from this image in markdown format."
    else:
        return "Describe this image."


def process_single_image(image_path: str, prompt: str, crop_height: int, overlap: int) -> dict:
    """
    단일 이미지 처리
    Returns: {"image_path": str, "ocr_text": str, "is_cropped": bool, "chunks": int}
    """
    try:
        # 크롭 처리
        cropped_paths = crop_image(image_path, crop_height, overlap)
        is_cropped = len(cropped_paths) > 1

        # 각 청크 처리
        all_texts = []
        for chunk_path in cropped_paths:
            # Base64 인코딩
            img_base64 = image_to_base64(chunk_path)

            # vLLM API 호출
            ocr_text, error_msg = call_vllm_api(img_base64, prompt)

            if error_msg:
                all_texts.append(f"[Error] {error_msg}")
            else:
                all_texts.append(ocr_text)

        # 결과 병합
        combined_text = "\n\n---\n\n".join(all_texts) if len(all_texts) > 1 else all_texts[0]

        return {
            "image_path": image_path,
            "cropped_paths": cropped_paths,
            "ocr_text": combined_text,
            "is_cropped": is_cropped,
            "chunks": len(cropped_paths)
        }
    except Exception as e:
        return {
            "image_path": image_path,
            "cropped_paths": [image_path],
            "ocr_text": f"[처리 실패] {str(e)}",
            "is_cropped": False,
            "chunks": 1
        }


def reset_other_tabs(active_tab):
    """활성 탭 이외 초기화"""
    # 각 탭의 초기 상태 반환
    file_reset = gr.update(value=None)
    url_reset = gr.update(value="")
    json_reset = gr.update(value=None)
    
    preview_reset = gr.update(value=None)
    summary_reset = "입력을 선택하세요"
    
    return file_reset, url_reset, json_reset, preview_reset, summary_reset


def scroll_to_results():
    """결과 영역으로 스크롤 (JavaScript)"""
    js = """
    () => {
        const resultsSection = document.querySelector('#results-section');
        if (resultsSection) {
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
    """
    return js


def create_download_file(panel_num: int, mode: str) -> Optional[str]:
    """
    패널 결과를 JSON 파일로 생성
    Returns: JSON 파일 경로
    """
    try:
        metadata = panel_results[panel_num]["metadata"]

        if not metadata:
            return None

        # JSON 데이터 생성
        download_data = {
            "panel": panel_num,
            "mode": mode,
            "timestamp": datetime.now().isoformat(),
            "results": [
                {
                    "image_index": idx + 1,
                    "image_name": Path(m["image_path"]).name,
                    "ocr_text": m["ocr_text"],
                    "is_cropped": m["is_cropped"],
                    "chunks": m["chunks"]
                }
                for idx, m in enumerate(metadata)
            ],
            "summary": {
                "total_images": len(metadata),
                "total_chunks": sum(m["chunks"] for m in metadata)
            }
        }

        # JSON 파일 저장
        json_path = TEMP_DIR / f"panel{panel_num}_result_{int(time.time())}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(download_data, f, ensure_ascii=False, indent=2)

        return str(json_path)
    except Exception as e:
        print(f"다운로드 파일 생성 실패: {str(e)}")
        return None


# ============================================================================
# 🎯 패널 생성 함수
# ============================================================================

def create_panel(panel_num):
    """각 패널의 UI 컴포넌트 생성"""
    with gr.Column(scale=1):
        # 작업 모드 선택 (Dropdown)
        mode = gr.Dropdown(
            choices=["OCR_PURE", "OCR_MD", "OCR_DESC", "CUSTOM"],
            value="OCR_PURE" if panel_num == 1 else "OCR_MD" if panel_num == 2 else "OCR_DESC",
            label=f"📝 Panel {panel_num} 작업 모드",
            info="처리 방식 선택",
            container=True
        )

        # CUSTOM 모드 프롬프트 입력
        custom_prompt = gr.Textbox(
            label="커스텀 프롬프트",
            placeholder="CUSTOM 모드일 때 사용할 프롬프트를 입력하세요",
            lines=2,
            visible=False,
            container=True
        )

        # 크롭 설정 (Accordion 없이 직접 배치)
        with gr.Row():
            crop_height = gr.Slider(
                minimum=800,
                maximum=3000,
                value=1800,
                step=100,
                label="크롭 높이 (px)"
            )
            overlap = gr.Slider(
                minimum=50,
                maximum=500,
                value=200,
                step=50,
                label="오버랩 (px)"
            )

        # 실행 버튼
        run_btn = gr.Button(
            f"▶️ Panel {panel_num} 실행",
            variant="primary",
            size="sm"
        )

        # CUSTOM 모드 토글
        def toggle_custom(mode_val):
            return gr.update(visible=(mode_val == "CUSTOM"))

        mode.change(
            fn=toggle_custom,
            inputs=[mode],
            outputs=[custom_prompt]
        )

        return {
            "mode": mode,
            "custom_prompt": custom_prompt,
            "crop_height": crop_height,
            "overlap": overlap,
            "run_btn": run_btn
        }


def create_result_panel(panel_num):
    """결과 표시 패널 생성"""
    with gr.Column(scale=1):
        # 진행 상황
        progress_text = gr.Textbox(
            label=f"🔄 Panel {panel_num} 진행",
            value="⏸️ 대기 중",
            lines=1,
            interactive=False,
            container=True
        )
        
        # 이미지 갤러리
        result_gallery = gr.Gallery(
            label=f"🖼️ 처리된 이미지 (Panel {panel_num})",
            columns=2,
            rows=2,
            height=250,
            object_fit="contain",
            show_label=True,
            container=True
        )
        
        # 선택된 이미지 정보
        selected_info = gr.Markdown(
            value="_이미지를 클릭하면 해당 결과가 표시됩니다_",
            container=True
        )
        
        # OCR 결과
        result_text = gr.Textbox(
            label="📄 OCR 결과",
            placeholder="처리 결과가 여기에 표시됩니다",
            lines=8,
            max_lines=15,
            container=True
        )
        
        # 다운로드
        download_btn = gr.Button("📥 결과 다운로드", size="sm")
        
        return {
            "progress_text": progress_text,
            "result_gallery": result_gallery,
            "selected_info": selected_info,
            "result_text": result_text,
            "download_btn": download_btn
        }


# ============================================================================
# 🎯 메인 UI
# ============================================================================

with gr.Blocks(
    title="OCR/Describe 이미지 처리 시스템"
) as demo:
    
    # ========================================================================
    # 헤더
    # ========================================================================
    gr.Markdown("""
    # 📸 OCR/Describe 이미지 처리 시스템 (3-Panel Demo)
    동일한 이미지로 3가지 설정을 동시에 비교 테스트할 수 있습니다.
    """)
    
    # ========================================================================
    # 입력 영역 (1:2 비율, 가로 분할)
    # ========================================================================
    with gr.Group(elem_id="input-section"):
        gr.Markdown("## 📥 입력")
        
        with gr.Row():
            # 왼쪽: 입력 탭 (1)
            with gr.Column(scale=1):
                with gr.Tabs() as input_tabs:
                    
                    # Tab 1: 이미지 파일
                    with gr.Tab("📁 파일/폴더", id=0) as tab_file:
                        file_input = gr.File(
                            label="이미지 선택 (다중 파일 또는 폴더)",
                            file_types=["image", ".png", ".jpg", ".jpeg", ".gif", ".webp"],
                            file_count="multiple",
                            type="filepath"
                        )
                        file_folder_input = gr.Textbox(
                            label="📂 또는 폴더 경로 입력",
                            placeholder="C:/Users/.../images 또는 /home/.../images",
                            lines=1
                        )
                        file_load_folder_btn = gr.Button("폴더에서 이미지 불러오기", size="sm")
                        file_product_id = gr.Textbox(
                            label="상품 번호 (선택)",
                            placeholder="예: MANUAL_001",
                            lines=1
                        )
                    
                    # Tab 2: URL
                    with gr.Tab("🔗 URL", id=1) as tab_url:
                        url_input = gr.Textbox(
                            label="이미지 URL",
                            placeholder="여러 URL은 쉼표(,)로 구분\n예: https://example.com/1.jpg, https://example.com/2.jpg",
                            lines=6
                        )
                        url_product_id = gr.Textbox(
                            label="상품 번호 (선택)",
                            placeholder="예: MANUAL_001",
                            lines=1
                        )
                        url_load_btn = gr.Button("🔄 URL에서 불러오기", size="sm", variant="primary")
                    
                    # Tab 3: JSON
                    with gr.Tab("📄 JSON", id=2) as tab_json:
                        json_input = gr.File(
                            label="JSON 파일 선택",
                            file_types=[".json"],
                            type="filepath"
                        )
                        gr.Markdown("""
                        **JSON 형식:**
```json
                        [
                          {
                            "godNo": "GR9125040764391",
                            "img_path": ["url1", "url2", ...]
                          }
                        ]
```
                        """)
            
            # 오른쪽: 입력 미리보기 (2)
            with gr.Column(scale=2):
                preview_gallery = gr.Gallery(
                    label="🖼️ 입력 미리보기",
                    columns=4,
                    rows=2,
                    height=300,
                    object_fit="contain",
                    show_label=True
                )
                input_summary = gr.Textbox(
                    label="📊 입력 요약",
                    value="이미지를 업로드하거나 URL/JSON을 입력하세요",
                    lines=2,
                    interactive=False
                )
    
    # ========================================================================
    # 실행 제어 영역
    # ========================================================================
    with gr.Group(elem_id="control-section"):
        with gr.Row():
            run_all_btn = gr.Button(
                "🚀 전체 실행 (3개 패널 모두)",
                variant="primary",
                size="lg",
                scale=3
            )
            execution_mode = gr.Radio(
                choices=["순차 실행", "병렬 실행"],
                value="순차 실행",
                label="실행 방식",
                scale=1
            )
    
    # ========================================================================
    # 패널 설정 영역 (3분할)
    # ========================================================================
    with gr.Group(elem_id="panels-section"):
        with gr.Row(equal_height=True):
            panel1 = create_panel(1)
            panel2 = create_panel(2)
            panel3 = create_panel(3)
    
    # ========================================================================
    # 결과 영역 (3분할)
    # ========================================================================
    gr.Markdown("---")
    gr.Markdown("## 📊 처리 결과", elem_id="results-section")
    
    with gr.Row(equal_height=False):
        result1 = create_result_panel(1)
        result2 = create_result_panel(2)
        result3 = create_result_panel(3)
    
    # ========================================================================
    # 전역 상태
    # ========================================================================
    global_images = gr.State([])
    global_product_ids = gr.State([])
    
    # ========================================================================
    # 🔧 이벤트 핸들러
    # ========================================================================
    
    def handle_file_upload(files, folder_path=None):
        """파일 또는 폴더에서 이미지 로드"""
        image_paths = []

        # 파일 업로드
        if files:
            for f in files:
                # Gradio 6.0: 파일은 문자열 경로로 전달됨
                if isinstance(f, str):
                    image_paths.append(f)
                elif hasattr(f, 'name'):
                    image_paths.append(f.name)
                else:
                    # 기타 경우 문자열 변환
                    path_str = str(f)
                    if path_str:
                        image_paths.append(path_str)

        # 폴더 경로
        elif folder_path and folder_path.strip():
            folder = Path(folder_path.strip())
            if folder.exists() and folder.is_dir():
                image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
                image_paths = [
                    str(p) for p in folder.rglob('*')
                    if p.suffix.lower() in image_exts
                ]
            else:
                return None, "❌ 폴더 경로가 유효하지 않습니다", []

        if not image_paths:
            return None, "이미지를 선택하세요", []

        return (
            image_paths,  # preview_gallery
            f"✅ 총 {len(image_paths)}개 이미지 로드됨",  # input_summary
            image_paths  # global_images
        )

    def handle_load_folder(folder_path):
        """폴더 버튼 클릭"""
        return handle_file_upload(None, folder_path)
    
    def handle_url_load(urls):
        """URL 로드"""
        if not urls or not urls.strip():
            return None, "URL을 입력하세요", []

        url_list = [u.strip() for u in urls.split(",") if u.strip()]

        # URL에서 이미지 다운로드
        downloaded_paths = []
        for url in url_list:
            img_path = download_image_from_url(url)
            if img_path:
                downloaded_paths.append(img_path)

        if not downloaded_paths:
            return None, "❌ 이미지 다운로드 실패", []

        return (
            downloaded_paths,  # preview_gallery
            f"✅ 총 {len(downloaded_paths)}개 이미지 다운로드됨 (입력: {len(url_list)}개)",  # input_summary
            downloaded_paths  # global_images
        )
    
    def handle_json_upload(json_file):
        """JSON 업로드"""
        if not json_file:
            return None, "JSON 파일을 선택하세요", []

        try:
            with open(json_file.name, 'r', encoding='utf-8') as f:
                data = json.load(f)

            total_products = len(data)

            # JSON에서 이미지 URL 추출 및 다운로드
            downloaded_paths = []
            for item in data:
                img_paths = item.get("img_path", [])
                for url in img_paths:
                    img_path = download_image_from_url(url)
                    if img_path:
                        downloaded_paths.append(img_path)

            if not downloaded_paths:
                return None, f"❌ 이미지 다운로드 실패 ({total_products}개 상품)", []

            return (
                downloaded_paths,  # preview_gallery
                f"✅ {total_products}개 상품, {len(downloaded_paths)}개 이미지 다운로드됨",  # input_summary
                downloaded_paths  # global_images
            )
        except Exception as e:
            return None, f"❌ JSON 오류: {str(e)}", []
    
    def handle_tab_change(evt: gr.SelectData):
        """탭 전환 시 다른 탭 초기화"""
        return (
            gr.update(value=None),  # file_input
            gr.update(value=""),    # url_input
            gr.update(value=None),  # json_input
            gr.update(value=None),  # preview_gallery
            "입력을 선택하세요",     # input_summary
            []  # global_images
        )
    
    def handle_panel_run(panel_num, mode, custom_prompt, crop_height, overlap, global_images):
        """개별 패널 실행 + 자동 스크롤"""
        if not global_images:
            return (
                "❌ 입력 이미지가 없습니다",
                None,
                "입력 탭에서 이미지를 먼저 로드하세요",
                ""
            )

        try:
            # 기본값 처리 (안전장치)
            crop_height = crop_height if crop_height is not None else 1800
            overlap = overlap if overlap is not None else 200

            # 프롬프트 로드
            prompt = load_prompt_template(mode, custom_prompt)

            # 진행 상황 초기화
            progress = f"⏳ Panel {panel_num} 처리 중... (0/{len(global_images)} 이미지)"

            # 각 이미지 처리
            results = []
            all_cropped_images = []

            for idx, img_path in enumerate(global_images):
                # 진행 상황 업데이트
                progress = f"⏳ Panel {panel_num} 처리 중... ({idx+1}/{len(global_images)} 이미지)"

                # 이미지 처리
                result = process_single_image(img_path, prompt, crop_height, overlap)
                results.append(result)

                # 크롭된 이미지들을 갤러리용으로 수집
                all_cropped_images.extend(result["cropped_paths"])

            # 결과 저장 (전역 상태)
            panel_results[panel_num]["images"] = all_cropped_images
            panel_results[panel_num]["texts"] = [r["ocr_text"] for r in results]
            panel_results[panel_num]["metadata"] = results

            # 첫 번째 이미지 결과 표시
            first_result_text = results[0]["ocr_text"] if results else ""

            return (
                f"✅ 처리 완료 ({len(global_images)}개 이미지, {len(all_cropped_images)}개 청크)",
                all_cropped_images,  # gallery
                f"**이미지 #1** 선택됨 (Panel {panel_num})",
                first_result_text
            )
        except Exception as e:
            return (
                f"❌ 처리 실패: {str(e)}",
                None,
                "",
                f"오류가 발생했습니다:\n{str(e)}"
            )
    
    def handle_gallery_select(panel_num):
        """갤러리 이미지 선택"""
        def inner(evt: gr.SelectData):
            idx = evt.index

            # 패널 결과에서 해당 인덱스의 텍스트 가져오기
            texts = panel_results[panel_num]["texts"]

            if idx < len(texts):
                result_text = texts[idx]
            else:
                result_text = f"이미지 #{idx + 1}의 OCR 결과\n\n(결과를 찾을 수 없습니다)"

            return (
                f"**이미지 #{idx + 1}** 선택됨 (Panel {panel_num})",
                result_text
            )
        return inner
    
    def handle_run_all(exec_mode, global_images,
                       mode1, custom1, crop1, overlap1,
                       mode2, custom2, crop2, overlap2,
                       mode3, custom3, crop3, overlap3):
        """전체 실행"""
        if not global_images:
            return "❌ 입력 이미지가 없습니다"

        try:
            # 기본값 처리 (안전장치)
            crop1 = crop1 if crop1 is not None else 1800
            overlap1 = overlap1 if overlap1 is not None else 200
            crop2 = crop2 if crop2 is not None else 1800
            overlap2 = overlap2 if overlap2 is not None else 200
            crop3 = crop3 if crop3 is not None else 1800
            overlap3 = overlap3 if overlap3 is not None else 200

            configs = [
                (mode1, custom1, crop1, overlap1),
                (mode2, custom2, crop2, overlap2),
                (mode3, custom3, crop3, overlap3)
            ]

            if exec_mode == "순차 실행":
                # 순차 실행: Panel 1 -> 2 -> 3
                for i, (mode, custom_prompt, crop_height, overlap) in enumerate(configs, 1):
                    handle_panel_run(i, mode, custom_prompt, crop_height, overlap, global_images)

                return f"✅ 전체 실행 완료 (순차, {len(global_images)}개 이미지)"
            else:
                # 병렬 실행: Thread 사용
                def run_panel_thread(panel_num, mode, custom_prompt, crop_height, overlap):
                    handle_panel_run(panel_num, mode, custom_prompt, crop_height, overlap, global_images)

                threads = []
                for i, (mode, custom_prompt, crop_height, overlap) in enumerate(configs, 1):
                    t = threading.Thread(target=run_panel_thread, args=(i, mode, custom_prompt, crop_height, overlap))
                    t.start()
                    threads.append(t)

                # 모든 스레드 완료 대기
                for t in threads:
                    t.join()

                return f"✅ 전체 실행 완료 (병렬, {len(global_images)}개 이미지)"
        except Exception as e:
            return f"❌ 전체 실행 실패: {str(e)}"
    
    # ========================================================================
    # 🔗 이벤트 연결
    # ========================================================================
    
    # 파일 업로드
    file_input.change(
        fn=handle_file_upload,
        inputs=[file_input, gr.State(None)],
        outputs=[preview_gallery, input_summary, global_images]
    )

    file_load_folder_btn.click(
        fn=handle_load_folder,
        inputs=[file_folder_input],
        outputs=[preview_gallery, input_summary, global_images]
    )

    # URL 로드
    url_load_btn.click(
        fn=handle_url_load,
        inputs=[url_input],
        outputs=[preview_gallery, input_summary, global_images]
    )

    # JSON 업로드
    json_input.change(
        fn=handle_json_upload,
        inputs=[json_input],
        outputs=[preview_gallery, input_summary, global_images]
    )
    
    # 탭 전환 시 초기화
    input_tabs.select(
        fn=handle_tab_change,
        outputs=[file_input, url_input, json_input, preview_gallery, input_summary, global_images]
    )
    
    # 개별 패널 실행
    def create_panel_handler(panel_num):
        def handler(mode, custom_prompt, crop_height, overlap, global_imgs):
            return handle_panel_run(panel_num, mode, custom_prompt, crop_height, overlap, global_imgs)
        return handler

    for i, (panel, result) in enumerate([(panel1, result1), (panel2, result2), (panel3, result3)], 1):
        panel["run_btn"].click(
            fn=create_panel_handler(i),
            inputs=[
                panel["mode"],
                panel["custom_prompt"],
                panel["crop_height"],
                panel["overlap"],
                global_images
            ],
            outputs=[
                result["progress_text"],
                result["result_gallery"],
                result["selected_info"],
                result["result_text"]
            ],
            js=scroll_to_results()  # 자동 스크롤
        )

        # 갤러리 선택
        result["result_gallery"].select(
            fn=handle_gallery_select(i),
            outputs=[result["selected_info"], result["result_text"]]
        )

        # 다운로드 버튼
        def create_download_handler(panel_num, panel):
            def handler():
                mode = panel["mode"].value if hasattr(panel["mode"], 'value') else "OCR_PURE"
                return create_download_file(panel_num, mode)
            return handler

        result["download_btn"].click(
            fn=lambda pnum=i, pnl=panel: create_download_file(pnum, pnl["mode"]),
            outputs=gr.File(label="결과 다운로드")
        )
    
    # 전체 실행
    run_all_btn.click(
        fn=handle_run_all,
        inputs=[
            execution_mode,
            global_images,
            # Panel 1 설정
            panel1["mode"], panel1["custom_prompt"], panel1["crop_height"], panel1["overlap"],
            # Panel 2 설정
            panel2["mode"], panel2["custom_prompt"], panel2["crop_height"], panel2["overlap"],
            # Panel 3 설정
            panel3["mode"], panel3["custom_prompt"], panel3["crop_height"], panel3["overlap"]
        ],
        outputs=[input_summary],
        js=scroll_to_results()  # 자동 스크롤
    )


# ============================================================================
# 🚀 실행
# ============================================================================

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        css="""
        #input-section { max-height: 350px; }
        #control-section { padding: 10px 0; }
        #panels-section { padding: 10px 0; }
        #results-section { margin-top: 20px; }
        .compact { margin: 5px 0 !important; }
        """
    )