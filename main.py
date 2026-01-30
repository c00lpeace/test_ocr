import gradio as gr
import json
from pathlib import Path

# ============================================================================
# 🎨 글로벌 상태 및 유틸리티
# ============================================================================

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
        
        # 크롭/저장 설정 (Accordion - 컴팩트)
        with gr.Accordion("⚙️ 고급 설정", open=False):
            with gr.Row():
                crop_height = gr.Slider(
                    minimum=800,
                    maximum=3000,
                    value=1800,
                    step=100,
                    label="크롭 높이",
                    info="px"
                )
                overlap = gr.Slider(
                    minimum=50,
                    maximum=500,
                    value=200,
                    step=50,
                    label="오버랩",
                    info="px"
                )
            save_permanent = gr.Checkbox(
                label="💾 영구 저장 (OFF: 자동삭제 / ON: 보관)",
                value=False
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
            "save_permanent": save_permanent,
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
            image_paths = [f.name if hasattr(f, 'name') else f for f in files]
        
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
                return None, "❌ 폴더 경로가 유효하지 않습니다"
        
        if not image_paths:
            return None, "이미지를 선택하세요"
        
        return (
            image_paths,
            f"✅ 총 {len(image_paths)}개 이미지 로드됨"
        )
    
    def handle_load_folder(folder_path):
        """폴더 버튼 클릭"""
        return handle_file_upload(None, folder_path)
    
    def handle_url_load(urls):
        """URL 로드"""
        if not urls or not urls.strip():
            return None, "URL을 입력하세요"
        
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        
        # TODO: 실제 다운로드 구현
        return (
            None,  # 다운로드한 이미지 경로
            f"✅ {len(url_list)}개 URL 입력됨 (다운로드 구현 필요)"
        )
    
    def handle_json_upload(json_file):
        """JSON 업로드"""
        if not json_file:
            return None, "JSON 파일을 선택하세요"
        
        try:
            with open(json_file.name, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            total_products = len(data)
            total_images = sum(len(item.get("img_path", [])) for item in data)
            
            # TODO: JSON에서 이미지 다운로드
            return (
                None,
                f"✅ {total_products}개 상품, {total_images}개 이미지 (다운로드 구현 필요)"
            )
        except Exception as e:
            return None, f"❌ JSON 오류: {str(e)}"
    
    def handle_tab_change(evt: gr.SelectData):
        """탭 전환 시 다른 탭 초기화"""
        # TODO: 현재 탭 이외 입력 초기화
        return (
            gr.update(value=None),  # file_input
            gr.update(value=""),    # url_input
            gr.update(value=None),  # json_input
            gr.update(value=None),  # preview_gallery
            "입력을 선택하세요"       # summary
        )
    
    def handle_panel_run(panel_num, mode, custom_prompt):
        """개별 패널 실행 + 자동 스크롤"""
        # TODO: 실제 처리
        progress = f"⏳ Panel {panel_num} 처리 중..."
        result_txt = f"Panel {panel_num}\n모드: {mode}\n결과 표시 영역"
        
        return (
            progress,
            None,  # gallery
            f"**Panel {panel_num}** 실행됨",
            result_txt
        )
    
    def handle_gallery_select(panel_num):
        """갤러리 이미지 선택"""
        def inner(evt: gr.SelectData):
            idx = evt.index
            return (
                f"**이미지 #{idx + 1}** 선택됨 (Panel {panel_num})",
                f"이미지 #{idx + 1}의 OCR 결과\n\n(실제 결과가 여기에 표시됩니다)"
            )
        return inner
    
    def handle_run_all(exec_mode):
        """전체 실행"""
        return f"🚀 전체 실행 시작 ({exec_mode})"
    
    # ========================================================================
    # 🔗 이벤트 연결
    # ========================================================================
    
    # 파일 업로드
    file_input.change(
        fn=handle_file_upload,
        inputs=[file_input, gr.State(None)],
        outputs=[preview_gallery, input_summary]
    )
    
    file_load_folder_btn.click(
        fn=handle_load_folder,
        inputs=[file_folder_input],
        outputs=[preview_gallery, input_summary]
    )
    
    # URL 로드
    url_load_btn.click(
        fn=handle_url_load,
        inputs=[url_input],
        outputs=[preview_gallery, input_summary]
    )
    
    # JSON 업로드
    json_input.change(
        fn=handle_json_upload,
        inputs=[json_input],
        outputs=[preview_gallery, input_summary]
    )
    
    # 탭 전환 시 초기화
    input_tabs.select(
        fn=handle_tab_change,
        outputs=[file_input, url_input, json_input, preview_gallery, input_summary]
    )
    
    # 개별 패널 실행
    for i, (panel, result) in enumerate([(panel1, result1), (panel2, result2), (panel3, result3)], 1):
        panel["run_btn"].click(
            fn=handle_panel_run,
            inputs=[gr.State(i), panel["mode"], panel["custom_prompt"]],
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
    
    # 전체 실행
    run_all_btn.click(
        fn=handle_run_all,
        inputs=[execution_mode],
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