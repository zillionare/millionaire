(function () {
            function modalContainer() {
                return document.getElementById('modal-container');
            }

            function modalElement(root) {
                if (!root) {
                    return null;
                }
                return root.querySelector('[data-uk-modal], .uk-modal');
            }

            function modalApi(element) {
                if (!element || !window.UIkit || typeof window.UIkit.modal !== 'function') {
                    return null;
                }
                return window.UIkit.modal(element);
            }

            function hideCurrentModal() {
                var container = modalContainer();
                var element = modalElement(container);
                var api = modalApi(element);
                if (api) {
                    api.hide();
                }
            }

            function clearModalContainer() {
                var container = modalContainer();
                if (!container) {
                    return;
                }
                hideCurrentModal();
                container.innerHTML = '';
            }

            function showInsertedModal(root) {
                var api = modalApi(modalElement(root));
                if (api) {
                    api.show();
                }
            }

            window.closeStrategyModal = clearModalContainer;

            document.body.addEventListener('htmx:beforeSwap', function (event) {
                if (event.target && event.target.id === 'modal-container') {
                    hideCurrentModal();
                }
            });

            document.body.addEventListener('htmx:afterSwap', function (event) {
                if (event.target && event.target.id === 'modal-container') {
                    showInsertedModal(event.target);
                }
            });
        })();
