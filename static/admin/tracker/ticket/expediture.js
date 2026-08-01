document.addEventListener( 'DOMContentLoaded', async () => {
	function updateTotal( div ) {
		let amountInputs = div.querySelectorAll( '.field-amount input' );
		let sum = 0;

		amountInputs.forEach( ( input ) => {
			if ( input.name && !input.name.includes( '__prefix__' ) ) {
				let val = parseFloat( input.value );
				if ( !isNaN( val ) ) {
					sum += val;
				}
			}
		} );

		sum = parseFloat( sum ).toFixed( 2 );
		let totalContainer = div.querySelector( '.total' );
		if ( totalContainer ) {
			totalContainer.innerHTML = `{% trans "Total" %}: <b>${ sum }</b>`;
		}
	}

	const preexpeditureDiv = document.querySelector( '#preexpediture_set-group' );
	const expeditureDiv = document.querySelector( '#expediture_set-wrapper' ) || document.querySelector( '#expediture_set-wrapper' );

	function updatePreexpediture() {
		updateTotal( preexpeditureDiv );
	}

	function updateExpediture() {
		updateTotal( expeditureDiv );
	}

	if ( preexpeditureDiv ) {
		preexpeditureDiv.addEventListener( 'input', updatePreexpediture );
	}
	if ( expeditureDiv ) {
		expeditureDiv.addEventListener( 'input', updateExpediture );
	}

	function togglePaymentDetails( selectElement ) {
		const inlineRow = selectElement.closest( '.inline-related' );
		if ( !inlineRow ) {
			return;
		}

		const fieldsets = inlineRow.querySelectorAll( 'fieldset.module' );

		fieldsets.forEach( ( fieldset ) => {
			const h2 = fieldset.querySelector( 'h2' );
			if ( h2 && h2.textContent.includes( 'Payment Details' ) ) {
				if ( selectElement.value === 'bank_transfer' ) {
					fieldset.style.display = 'block';
				} else {
					fieldset.style.display = 'none';
				}
			}
		} );
	}

	function toggleCofinanceAccount( ticketSelect ) {
		const inlineRow = ticketSelect.closest( '.inline-related' );
		if ( !inlineRow ) {
			return;
		}

		const accountFieldBox = inlineRow.querySelector( '.fieldBox.field-cofinance_source_account' );

		if ( accountFieldBox ) {
			if ( ticketSelect.value !== '' ) {
				accountFieldBox.style.display = 'none';
				const accountInput = accountFieldBox.querySelector( 'input' );
				if ( accountInput ) {
					accountInput.value = '';
				}
			} else {
				accountFieldBox.style.display = '';
			}
		}
	}

	function filterTicketsByGrant( grantSelect ) {
		const selectedGrant = grantSelect.value;
		const inlineRow = grantSelect.closest( '.inline-related' );
		const ticketSelect = inlineRow.querySelector( 'select[id$="-cofinance_source_ticket"]' );

		if ( !ticketSelect ) {
			return;
		}

		const mappingData = ticketSelect.getAttribute( 'data-ticket-grants' );
		const mapping = mappingData ? JSON.parse( mappingData ) : {};

		Array.from( ticketSelect.options ).forEach( ( opt ) => {
			if ( opt.value === '' ) {
				opt.hidden = false;
				opt.disabled = false;
				return;
			}

			if ( !selectedGrant || mapping[ opt.value ] === selectedGrant ) {
				opt.hidden = false;
				opt.disabled = false;
			} else {
				opt.hidden = true;
				opt.disabled = true;
			}
		} );

		if ( ticketSelect.value && mapping[ ticketSelect.value ] !== selectedGrant && selectedGrant !== '' ) {
			ticketSelect.value = '';
			ticketSelect.dispatchEvent( new Event( 'change', { bubbles: true } ) );
		}
	}

	const paymentTypeSelects = document.querySelectorAll( 'select[id$="-payment_type"]' );
	paymentTypeSelects.forEach( select => togglePaymentDetails( select ) );

	const ticketSelects = document.querySelectorAll( 'select[id$="-cofinance_source_ticket"]' );
	ticketSelects.forEach( select => toggleCofinanceAccount( select ) );

	const grantSelects = document.querySelectorAll( 'select[id$="-cofinance_filter_grant"]' );
	grantSelects.forEach( select => filterTicketsByGrant( select ) );

	document.addEventListener( 'change', ( e ) => {
		if ( e.target && e.target.id.includes( '-payment_type' ) ) {
			togglePaymentDetails( e.target );
		}
		if ( e.target && e.target.id.includes( '-cofinance_source_ticket' ) ) {
			toggleCofinanceAccount( e.target );
		}
		if ( e.target && e.target.id.includes( 'cofinance_filter_grant' ) ) {
			filterTicketsByGrant( e.target );
		}
	} );

	document.addEventListener( 'change', ( e ) => {
		if ( e.target && e.target.name.endsWith( '-template_choice' ) ) {
			const select = e.target;
			const templates = JSON.parse( select.getAttribute( 'data-templates' ) || '{}' );
			const selectedId = select.value;
			const template = templates[ selectedId ];

			if ( template ) {
				const prefix = select.name.replace( 'template_choice', '' );

				/* eslint-disable camelcase */
				const fields = {
					saved_account: template.saved_account,
					account_number: template.account_number,
					variable_symbol: template.variable_symbol,
					specific_symbol: template.specific_symbol,
					constant_symbol: template.constant_symbol,
					amount: template.amount
				};
				/* eslint-enable camelcase */

				for ( const [ key, value ] of Object.entries( fields ) ) {
					const input = document.querySelector( `[name="${ prefix }${ key }"]` );
					if ( input ) {
						input.value = value;
						input.dispatchEvent( new Event( 'change', { bubbles: true } ) );
					}
				}

				const typeSelect = document.querySelector( `[name="${ prefix }payment_type"]` );
				if ( typeSelect ) {
					typeSelect.value = 'bank_transfer';
					typeSelect.dispatchEvent( new Event( 'change', { bubbles: true } ) );
				}
			}
		}
	} );
} );
