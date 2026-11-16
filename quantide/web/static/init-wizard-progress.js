(function() {
                const progressBar = document.getElementById('sync-progress-bar');
                const stageText = document.getElementById('sync-stage');
                const statusText = document.getElementById('sync-status');
                const returnButton = document.getElementById('sync-return-button');

                function renderWizardError(message) {
                    const headerRegion = document.getElementById('wizard-header-region');
                    if (!headerRegion) {
                        return;
                    }
                    let errorNode = document.getElementById('wizard-download-error');
                    if (!errorNode) {
                        errorNode = document.createElement('div');
                        errorNode.id = 'wizard-download-error';
                        errorNode.className = 'mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700';
                        headerRegion.appendChild(errorNode);
                    }
                    errorNode.textContent = message;
                }

                function showReturnButton() {
                    if (!returnButton) {
                        return;
                    }
                    returnButton.style.display = 'inline-flex';
                    returnButton.onclick = function() {
                        document.querySelector('.sync-dialog-container')?.remove();
                    };
                }

                // 创建 EventSource 连接
                const evtSource = new EventSource('/init-wizard/sync-progress');

                evtSource.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);

                        // 更新进度条
                        progressBar.style.width = data.progress + '%';
                        statusText.textContent = data.message || '等待同步进度...';
                        stageText.textContent = data.stage || '正在同步数据...';

                        // 检查是否完成
                        if (data.completed) {
                            evtSource.close();
                            // 同步完成后自动跳转到完成页面
                            setTimeout(function() {
                                window.location.href = '/init-wizard/complete';
                            }, 1000);
                        }

                        // 检查是否有错误
                        if (data.error) {
                            statusText.textContent = '同步失败: ' + data.error;
                            statusText.classList.add('text-red-500');
                            stageText.textContent = '同步失败';
                            renderWizardError('下载失败：' + data.error);
                            showReturnButton();
                            evtSource.close();
                        }
                    } catch (e) {
                        console.error('解析进度数据失败:', e);
                    }
                };

                evtSource.onerror = function(err) {
                    console.error('SSE 连接错误:', err);
                    statusText.textContent = '同步连接异常，请稍后重试';
                    statusText.classList.add('text-red-500');
                    stageText.textContent = '同步连接异常';
                    renderWizardError('下载失败：同步连接异常，请稍后重试');
                    showReturnButton();
                };
            })();
