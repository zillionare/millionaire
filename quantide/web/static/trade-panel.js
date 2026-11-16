(function() {
                    const form = document.getElementById('trade-form');
                    const priceMode = document.getElementById('price-mode-select');
                    const priceInput = document.getElementById('price-input');
                    const orderModeAmount = document.getElementById('order-mode-amount');
                    const orderModeQuantity = document.getElementById('order-mode-quantity');
                    const valueLabel = document.getElementById('value-label');
                    const valueInput = document.getElementById('value-input');
                    const estShares = document.getElementById('est-shares');
                    const sideInput = document.getElementById('side-input');
                    const btnBuy = document.getElementById('btn-buy');
                    const btnSell = document.getElementById('btn-sell');
                    const buyStar = document.getElementById('buy-star');
                    const sellStar = document.getElementById('sell-star');
                    const priceChangeHint = document.getElementById('price-change-hint');
                    const formSubmit = document.getElementById('form-submit');
                    const cash = parseFloat(form.dataset.cash) || 0;
                    const assetDisplay = document.getElementById('asset-display');
                    const assetCode = document.getElementById('asset-code');
                    let searchDropdown = document.getElementById('asset-search-dropdown');
                    const referenceValues = {
                        close: document.getElementById('ref-close'),
                        ma5: document.getElementById('ref-ma5'),
                        ma10: document.getElementById('ref-ma10'),
                        ma20: document.getElementById('ref-ma20'),
                        ma30: document.getElementById('ref-ma30'),
                        ma60: document.getElementById('ref-ma60'),
                        current: document.getElementById('ref-current'),
                    };
                    let selectedAssetStats = null;
                    let activeSearchIndex = -1;
                    let limitPlaceholderPrice = '';
                    let lastQuickPricePct = null;
                    let lastQuickPriceValue = '';
                    let currentQuotePollId = null;

                    function refreshSearchDropdown() {
                        searchDropdown = document.getElementById('asset-search-dropdown');
                        return searchDropdown;
                    }

                    function getSearchItems() {
                        const dropdown = refreshSearchDropdown();
                        if (!dropdown) {
                            return [];
                        }
                        return Array.from(dropdown.querySelectorAll('.asset-search-item'));
                    }

                    function hideSearchDropdown() {
                        activeSearchIndex = -1;
                        const dropdown = refreshSearchDropdown();
                        if (!dropdown) {
                            return;
                        }
                        dropdown.classList.add('hidden');
                        dropdown.innerHTML = '';
                    }

                    function setActiveSearchIndex(index) {
                        const items = getSearchItems();
                        if (!items.length) {
                            activeSearchIndex = -1;
                            return;
                        }
                        const normalizedIndex = Math.max(0, Math.min(index, items.length - 1));
                        activeSearchIndex = normalizedIndex;
                        items.forEach(function(item, itemIndex) {
                            item.classList.toggle('bg-gray-100', itemIndex === normalizedIndex);
                            item.classList.toggle('dark:bg-gray-700', itemIndex === normalizedIndex);
                        });
                    }

                    function setReferenceText(key, value) {
                        const node = referenceValues[key];
                        if (node) {
                            node.textContent = value || '';
                        }
                    }

                    function clearReferencePrices() {
                        selectedAssetStats = null;
                        limitPlaceholderPrice = '';
                        clearQuickPriceSelection();
                        stopLiveQuotePolling();
                        Object.values(referenceValues).forEach(function(node) {
                            if (node) {
                                node.textContent = '';
                            }
                        });
                        updateLimitPricePlaceholder();
                        updatePriceChangeHint();
                        updateQuickPriceAvailability();
                    }

                    function updateCurrentReferencePrice() {
                        const node = referenceValues.current;
                        if (!node) {
                            return;
                        }
                        if (!selectedAssetStats) {
                            node.textContent = '';
                            return;
                        }
                        node.textContent = selectedAssetStats.current || '';
                    }

                    function clearQuickPriceSelection() {
                        lastQuickPricePct = null;
                        lastQuickPriceValue = '';
                    }

                    function getReferenceClosePrice() {
                        if (selectedAssetStats) {
                            const closePrice = parseFloat(selectedAssetStats.close || '');
                            if (!isNaN(closePrice) && closePrice > 0) {
                                return closePrice;
                            }
                        }
                        const placeholderPrice = parseFloat(limitPlaceholderPrice || '');
                        return !isNaN(placeholderPrice) && placeholderPrice > 0 ? placeholderPrice : 0;
                    }

                    function getCurrentQuotePrice() {
                        if (!selectedAssetStats) {
                            return 0;
                        }
                        const currentPrice = parseFloat(selectedAssetStats.current || '');
                        return !isNaN(currentPrice) && currentPrice > 0 ? currentPrice : 0;
                    }

                    function setLimitPlaceholderPrice(value) {
                        const parsed = parseFloat(value || '');
                        if (isNaN(parsed) || parsed <= 0) {
                            limitPlaceholderPrice = '';
                        } else {
                            limitPlaceholderPrice = parsed.toFixed(2);
                        }
                        updateLimitPricePlaceholder();
                    }

                    function updateLimitPricePlaceholder() {
                        if (priceMode.value === 'MARKET') {
                            priceInput.placeholder = '市价';
                            return;
                        }
                        priceInput.placeholder = limitPlaceholderPrice || '价格';
                    }

                    function updatePriceChangeHint() {
                        if (priceMode.value !== 'LIMIT') {
                            priceChangeHint.textContent = '';
                            return;
                        }
                        if (lastQuickPricePct !== null && priceInput.value === lastQuickPriceValue) {
                            const quickPct = lastQuickPricePct * 100;
                            const sign = quickPct > 0 ? '+' : '';
                            priceChangeHint.textContent = sign + quickPct.toFixed(2) + '%';
                            return;
                        }
                        const closePrice = parseFloat(selectedAssetStats && selectedAssetStats.close || '');
                        const limitPrice = parseFloat(priceInput.value);
                        if (isNaN(closePrice) || closePrice <= 0 || isNaN(limitPrice) || limitPrice <= 0) {
                            priceChangeHint.textContent = '';
                            return;
                        }
                        const deltaPct = ((limitPrice - closePrice) / closePrice) * 100;
                        const sign = deltaPct > 0 ? '+' : '';
                        priceChangeHint.textContent = sign + deltaPct.toFixed(2) + '%';
                    }

                    function setQuickPriceButtonsEnabled(enabled) {
                        document.querySelectorAll('.quick-price-btn').forEach(function(btn) {
                            btn.disabled = !enabled;
                        });
                    }

                    function setReferencePriceButtonsEnabled(enabled) {
                        document.querySelectorAll('.reference-price-btn').forEach(function(btn) {
                            const valueNode = btn.querySelector('[id^="ref-"]');
                            const hasValue = !!(valueNode && valueNode.textContent.trim() !== '');
                            btn.disabled = !(enabled && hasValue);
                        });
                    }

                    function updateQuickPriceAvailability() {
                        const hasAsset = !!assetCode.value;
                        const hasBasePrice = getReferenceClosePrice() > 0;
                        setQuickPriceButtonsEnabled(hasAsset && hasBasePrice);
                        setReferencePriceButtonsEnabled(hasAsset);
                    }

                    async function refreshLiveQuote(asset) {
                        if (!asset) {
                            return;
                        }
                        try {
                            const response = await fetch('/trade/live-quote?asset=' + encodeURIComponent(asset), {
                                headers: {'X-Requested-With': 'fetch'}
                            });
                            if (!response.ok || assetCode.value !== asset) {
                                return;
                            }
                            const payload = await response.json();
                            if (!selectedAssetStats) {
                                selectedAssetStats = {};
                            }
                            selectedAssetStats.current = payload.current || '';
                            updateCurrentReferencePrice();
                            updateQuickPriceAvailability();
                            updateQuickPrices();
                            updateEstShares();
                        } catch (error) {
                            updateQuickPriceAvailability();
                        }
                    }

                    function stopLiveQuotePolling() {
                        if (currentQuotePollId !== null) {
                            clearInterval(currentQuotePollId);
                            currentQuotePollId = null;
                        }
                    }

                    function startLiveQuotePolling(asset) {
                        stopLiveQuotePolling();
                        if (!asset) {
                            return;
                        }
                        refreshLiveQuote(asset);
                        currentQuotePollId = setInterval(function() {
                            refreshLiveQuote(asset);
                        }, 3000);
                    }

                    function applyReferencePrices(stats) {
                        if (!stats || !stats.visible) {
                            clearReferencePrices();
                            return;
                        }
                        selectedAssetStats = stats;
                        const referencePrice = stats.current || stats.close || '';
                        setLimitPlaceholderPrice(referencePrice);
                        const referenceParsed = parseFloat(referencePrice);
                        if (
                            priceMode.value === 'LIMIT'
                            && !priceInput.value.trim()
                            && !isNaN(referenceParsed)
                            && referenceParsed > 0
                        ) {
                            priceInput.value = referenceParsed.toFixed(2);
                            clearQuickPriceSelection();
                        }
                        setReferenceText('close', stats.close);
                        setReferenceText('ma5', stats.ma5);
                        setReferenceText('ma10', stats.ma10);
                        setReferenceText('ma20', stats.ma20);
                        setReferenceText('ma30', stats.ma30);
                        setReferenceText('ma60', stats.ma60);
                        updateCurrentReferencePrice();
                        updateQuickPrices();
                        updatePriceChangeHint();
                        updateQuickPriceAvailability();
                        updateEstShares();
                    }

                    async function fetchAssetStats(asset) {
                        if (!asset) {
                            clearReferencePrices();
                            return;
                        }
                        try {
                            const response = await fetch('/trade/asset-stats?asset=' + encodeURIComponent(asset), {
                                headers: {'X-Requested-With': 'fetch'}
                            });
                            if (!response.ok) {
                                clearReferencePrices();
                                return;
                            }
                            const stats = await response.json();
                            if (assetCode.value !== asset) {
                                return;
                            }
                            applyReferencePrices(stats);
                        } catch (error) {
                            clearReferencePrices();
                        }
                    }

                    function updatePriceMode() {
                        if (priceMode.value === 'MARKET') {
                            priceInput.disabled = true;
                            priceInput.value = '';
                            priceInput.classList.add('bg-gray-100');
                        } else {
                            priceInput.disabled = false;
                            priceInput.classList.remove('bg-gray-100');
                        }
                        updateLimitPricePlaceholder();
                        updatePriceChangeHint();
                        updateEstShares();
                    }

                    function updateLabel() {
                        const side = sideInput.value;
                        const mode = document.querySelector('input[name="order_mode"]:checked').value;
                        if (side === 'BUY') {
                            valueLabel.textContent = mode === 'AMOUNT' ? '买入金额（万元）' : '买入手数';
                        } else {
                            valueLabel.textContent = mode === 'AMOUNT' ? '卖出金额（万元）' : '卖出手数';
                        }
                    }

                    function updateActiveSide() {
                        const side = sideInput.value;
                        if (side === 'BUY') {
                            buyStar.classList.remove('hidden');
                            btnBuy.classList.remove('opacity-60');
                            btnBuy.setAttribute('aria-pressed', 'true');
                            btnSell.classList.add('opacity-60');
                            btnSell.setAttribute('aria-pressed', 'false');
                            sellStar.classList.add('hidden');
                        } else {
                            buyStar.classList.add('hidden');
                            btnSell.classList.remove('opacity-60');
                            btnSell.setAttribute('aria-pressed', 'true');
                            btnBuy.classList.add('opacity-60');
                            btnBuy.setAttribute('aria-pressed', 'false');
                            sellStar.classList.remove('hidden');
                        }
                    }

                    function setOrderMode(mode) {
                        const useQuantity = mode === 'QUANTITY';
                        orderModeAmount.checked = !useQuantity;
                        orderModeQuantity.checked = useQuantity;
                    }

                    function resetTradeDraftForSideSwitch() {
                        setOrderMode('AMOUNT');
                        priceMode.value = 'LIMIT';
                        priceInput.value = '';
                        updatePriceMode();
                        valueInput.value = '';
                        updateLabel();
                        updateEstShares();
                        updateCurrentReferencePrice();
                        updateQuickPrices();
                    }

                    function activateTradeSide(nextSide, resetDraft) {
                        const changed = sideInput.value !== nextSide;
                        sideInput.value = nextSide;
                        updateActiveSide();
                        updateLabel();
                        if (changed && resetDraft) {
                            resetTradeDraftForSideSwitch();
                        }
                    }

                    function handleTradeSubmitIntent(nextSide) {
                        if (sideInput.value !== nextSide) {
                            activateTradeSide(nextSide, true);
                            return;
                        }
                        formSubmit.click();
                    }

                    function getEstimatePrice() {
                        const limitPrice = parseFloat(priceInput.value) || 0;
                        if (priceMode.value !== 'MARKET' && limitPrice > 0) {
                            return limitPrice;
                        }
                        const currentPrice = getCurrentQuotePrice();
                        if (currentPrice > 0) {
                            return currentPrice;
                        }
                        const closePrice = getReferenceClosePrice();
                        if (closePrice > 0) {
                            return closePrice;
                        }
                        return limitPrice > 0 ? limitPrice : 0;
                    }

                    function updateEstShares() {
                        const value = parseFloat(valueInput.value) || 0;
                        const mode = document.querySelector('input[name="order_mode"]:checked').value;

                        if (value <= 0) {
                            estShares.textContent = '';
                            return;
                        }

                        let shares;
                        if (mode === 'AMOUNT') {
                            const price = getEstimatePrice();
                            if (price <= 0) {
                                estShares.textContent = '';
                                return;
                            }
                            const amountYuan = value * 10000;
                            shares = Math.floor(amountYuan / price / 100) * 100;
                        } else {
                            shares = Math.floor(value) * 100;
                        }

                        estShares.textContent = shares > 0 ? (shares + ' 股') : '';
                    }

                    function getQuickPriceBase() {
                        if (selectedAssetStats) {
                            const closePrice = parseFloat(selectedAssetStats.close || '');
                            if (!isNaN(closePrice) && closePrice > 0) {
                                return closePrice;
                            }
                        }
                        return 0;
                    }

                    function setPosition(fraction) {
                        const mode = document.querySelector('input[name="order_mode"]:checked').value;
                        const amountYuan = cash * fraction;

                        if (mode === 'AMOUNT') {
                            valueInput.value = (amountYuan / 10000).toFixed(4).replace(/\.?0+$/, '');
                        } else {
                            const price = getEstimatePrice();
                            if (price <= 0) {
                                return;
                            }
                            const shares = Math.floor(amountYuan / price / 100) * 100;
                            valueInput.value = Math.floor(shares / 100);
                        }

                        updateEstShares();
                    }

                    // Event listeners
                    priceMode.addEventListener('change', updatePriceMode);
                    orderModeAmount.addEventListener('change', function() {
                        updateLabel();
                        updateEstShares();
                    });
                    orderModeQuantity.addEventListener('change', function() {
                        updateLabel();
                        updateEstShares();
                    });
                    valueInput.addEventListener('input', updateEstShares);
                    priceInput.addEventListener('input', updateEstShares);

                    btnBuy.addEventListener('click', function() {
                        handleTradeSubmitIntent('BUY');
                    });

                    btnSell.addEventListener('click', function() {
                        handleTradeSubmitIntent('SELL');
                    });

                    document.querySelectorAll('.pos-btn').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            setPosition(parseFloat(this.dataset.fraction));
                        });
                    });

                    document.querySelectorAll('.reference-price-btn').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            if (this.disabled || !selectedAssetStats) {
                                return;
                            }
                            const refKey = this.dataset.refKey;
                            const nextPrice = selectedAssetStats[refKey] || '';
                            const parsed = parseFloat(nextPrice);
                            if (isNaN(parsed) || parsed <= 0) {
                                return;
                            }
                            clearQuickPriceSelection();
                            priceMode.value = 'LIMIT';
                            updatePriceMode();
                            priceInput.value = parsed.toFixed(2);
                            updateEstShares();
                            updatePriceChangeHint();
                            updateQuickPrices();
                        });
                    });

                    // --- Asset search dropdown handlers ---
                    function selectAsset(item) {
                        assetDisplay.value = item.dataset.display;
                        assetCode.value = item.dataset.asset;
                        hideSearchDropdown();
                        // Auto-fill price if available
                        const price = item.dataset.price;
                        if (price && price !== '') {
                            setLimitPlaceholderPrice(price);
                        }
                        clearQuickPriceSelection();
                        priceInput.value = '';
                        updatePriceChangeHint();
                        updateEstShares();
                        updateQuickPrices();
                        fetchAssetStats(item.dataset.asset);
                        startLiveQuotePolling(item.dataset.asset);
                    }

                    function hydrateTradeFromPosition(row) {
                        const asset = row.dataset.asset || '';
                        if (!asset) {
                            return;
                        }
                        const rowPrice = parseFloat(row.dataset.price || '');
                        assetDisplay.value = row.dataset.display || asset;
                        assetCode.value = asset;
                        hideSearchDropdown();
                        priceMode.value = 'LIMIT';
                        clearQuickPriceSelection();
                        if (!isNaN(rowPrice) && rowPrice > 0) {
                            priceInput.value = rowPrice.toFixed(2);
                        } else {
                            priceInput.value = '';
                        }
                        updatePriceMode();
                        setLimitPlaceholderPrice(
                            !isNaN(rowPrice) && rowPrice > 0 ? rowPrice.toFixed(2) : ''
                        );
                        const availLots = parseFloat(row.dataset.availLots || '');
                        const canSell = !isNaN(availLots) && availLots > 0;
                        if (canSell) {
                            setOrderMode('QUANTITY');
                            valueInput.value = String(availLots);
                            activateTradeSide('SELL', false);
                        } else {
                            setOrderMode('AMOUNT');
                            valueInput.value = '';
                        }
                        updateLabel();
                        updateEstShares();
                        updateCurrentReferencePrice();
                        updateQuickPrices();
                        fetchAssetStats(asset);
                        startLiveQuotePolling(asset);
                    }

                    document.body.addEventListener('htmx:afterSwap', function(evt) {
                        if (evt.detail.target.id === 'asset-search-dropdown') {
                            const items = getSearchItems();
                            if (items.length === 1) {
                                selectAsset(items[0]);
                                return;
                            }
                            const dropdown = refreshSearchDropdown();
                            if (dropdown && dropdown.innerText.trim() !== '') {
                                dropdown.classList.remove('hidden');
                                setActiveSearchIndex(0);
                            }
                        }
                    });

                    document.body.addEventListener('click', function(evt) {
                        const sellTrigger = evt.target.closest('.position-sell-btn');
                        if (sellTrigger) {
                            evt.preventDefault();
                            evt.stopPropagation();
                            const positionRow = sellTrigger.closest('.trade-position-row');
                            if (positionRow) {
                                hydrateTradeFromPosition(positionRow);
                            }
                            return;
                        }
                        const item = evt.target.closest('.asset-search-item');
                        if (!item) {
                            return;
                        }
                        evt.preventDefault();
                        selectAsset(item);
                    });

                    document.body.addEventListener('dblclick', function(evt) {
                        const positionRow = evt.target.closest('.trade-position-row');
                        if (!positionRow) {
                            return;
                        }
                        evt.preventDefault();
                        hydrateTradeFromPosition(positionRow);
                    });

                    document.body.addEventListener('keydown', function(evt) {
                        const item = evt.target.closest('.asset-search-item');
                        if (!item || (evt.key !== 'Enter' && evt.key !== ' ')) {
                            return;
                        }
                        evt.preventDefault();
                        evt.stopPropagation();
                        selectAsset(item);
                    });

                    // Close dropdown when clicking outside
                    document.addEventListener('click', function(evt) {
                        const dropdown = refreshSearchDropdown();
                        if (!dropdown) {
                            return;
                        }
                        if (!assetDisplay.contains(evt.target) && !dropdown.contains(evt.target)) {
                            searchDropdown.classList.add('hidden');
                        }
                    });

                    // Clear hidden code when user manually edits display field
                    assetDisplay.addEventListener('input', function() {
                        assetCode.value = '';
                        clearReferencePrices();
                        priceInput.value = '';
                        if (assetDisplay.value.trim() === '') {
                            hideSearchDropdown();
                        }
                        updateQuickPrices();
                    });

                    assetDisplay.addEventListener('keydown', function(evt) {
                        const items = getSearchItems();
                        const dropdownVisible = !searchDropdown.classList.contains('hidden') && items.length > 0;
                        if (evt.key === 'Escape') {
                            evt.preventDefault();
                            hideSearchDropdown();
                            return;
                        }
                        if (evt.key === 'ArrowDown' && dropdownVisible) {
                            evt.preventDefault();
                            setActiveSearchIndex(activeSearchIndex + 1);
                            return;
                        }
                        if (evt.key === 'ArrowUp' && dropdownVisible) {
                            evt.preventDefault();
                            setActiveSearchIndex(activeSearchIndex - 1);
                            return;
                        }
                        if (evt.key !== 'Enter') {
                            return;
                        }
                        evt.preventDefault();
                        evt.stopPropagation();
                        if (!dropdownVisible) {
                            return;
                        }
                        const selectedItem = items[Math.max(activeSearchIndex, 0)];
                        if (selectedItem) {
                            selectAsset(selectedItem);
                        }
                    });

                    // --- Quick price button handlers ---
                    function updateQuickPrices() {
                        const basePrice = getQuickPriceBase();
                        document.querySelectorAll('.quick-price-btn').forEach(function(btn) {
                            const display = btn.querySelector('.quick-price-display');
                            const pct = parseFloat(btn.dataset.pct);
                            if (basePrice <= 0 || isNaN(pct)) {
                                display.textContent = '';
                                return;
                            }
                            const newPrice = basePrice * (1 + pct);
                            display.textContent = newPrice.toFixed(2);
                        });
                    }

                    // Click quick price button to set price
                    document.querySelectorAll('.quick-price-btn').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            if (this.disabled) {
                                return;
                            }
                            const basePrice = getQuickPriceBase();
                            const pct = parseFloat(this.dataset.pct);
                            if (this.dataset.marketOrder === 'true') {
                                clearQuickPriceSelection();
                                const display = this.querySelector('.quick-price-display');
                                priceMode.value = 'MARKET';
                                updatePriceMode();
                                if (display && display.textContent.trim() !== '') {
                                    priceInput.value = display.textContent.trim();
                                }
                                updateCurrentReferencePrice();
                                updateQuickPrices();
                                return;
                            }
                            if (basePrice > 0 && !isNaN(pct)) {
                                const nextPrice = (basePrice * (1 + pct)).toFixed(2);
                                priceMode.value = 'LIMIT';
                                updatePriceMode();
                                priceInput.value = nextPrice;
                                lastQuickPricePct = pct;
                                lastQuickPriceValue = nextPrice;
                                updateEstShares();
                                updateCurrentReferencePrice();
                                updatePriceChangeHint();
                                updateQuickPrices();
                            }
                        });
                    });

                    // Click reference price button (placeholder)
                    document.querySelectorAll('.ref-price-btn').forEach(function(btn) {
                        btn.addEventListener('click', function() {
                            // Reference price buttons are placeholders
                            // In a real implementation, these would fetch
                            // 昨收/MA5/MA10/etc. from market data
                        });
                    });

                    // Update quick price displays when price changes
                    priceInput.addEventListener('input', function() {
                        if (priceInput.value !== lastQuickPriceValue) {
                            clearQuickPriceSelection();
                        }
                        updateQuickPrices();
                        updateCurrentReferencePrice();
                        updatePriceChangeHint();
                    });

                    function layoutQuickGrid() {
                        const panel = document.getElementById('trade-order-panel');
                        const grid = document.getElementById('quick-price-grid');
                        if (!panel || !grid) {
                            return;
                        }
                        const gap = 6;
                        const height = panel.getBoundingClientRect().height;
                        if (height <= 0) {
                            return;
                        }
                        const size = (height - gap * 4) / 5;
                        const width = size * 4 + gap * 3;
                        const sizePx = size.toFixed(2) + 'px';
                        grid.style.width = width.toFixed(2) + 'px';
                        grid.style.height = height.toFixed(2) + 'px';
                        grid.style.gridTemplateColumns = 'repeat(4, ' + sizePx + ')';
                        grid.style.gridTemplateRows = 'repeat(5, ' + sizePx + ')';
                        grid.style.gap = gap + 'px';
                        grid.querySelectorAll('.quick-price-btn').forEach(function(btn) {
                            btn.style.width = sizePx;
                            btn.style.height = sizePx;
                        });
                    }

                    const orderPanel = document.getElementById('trade-order-panel');
                    if (window.ResizeObserver && orderPanel) {
                        new ResizeObserver(layoutQuickGrid).observe(orderPanel);
                    }
                    window.addEventListener('resize', layoutQuickGrid);

                    // Initial state
                    clearReferencePrices();
                    setQuickPriceButtonsEnabled(false);
                    updateActiveSide();
                    updateLabel();
                    updateEstShares();
                    updateQuickPrices();
                    layoutQuickGrid();
                    requestAnimationFrame(layoutQuickGrid);
                })();
