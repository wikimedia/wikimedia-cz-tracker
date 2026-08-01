/* global DateTimeShortcuts, SelectFilter */
window.initExpenditureFormset = function ( config ) {
	document.addEventListener( 'DOMContentLoaded', () => {
		const rows = '#' + config.prefix + '-group fieldset .formset-row-group';

		const reinitDateTimeShortCuts = () => {
			if ( typeof DateTimeShortcuts !== 'undefined' ) {
				$( '.datetimeshortcuts' ).remove();
				DateTimeShortcuts.init();
			}
		};
		const updateSelectFilter = () => {
			if ( typeof SelectFilter !== 'undefined' ) {
				$( '.selectfilter' ).each( ( index, value ) => {
					const nameArr = value.name.split( '-' );
					SelectFilter.init( value.id, nameArr[ nameArr.length - 1 ], false, config.staticUrl + 'admin/' );
				} );
				$( '.selectfilterstacked' ).each( ( index, value ) => {
					const nameArr = value.name.split( '-' );
					SelectFilter.init( value.id, nameArr[ nameArr.length - 1 ], true, config.staticUrl + 'admin/' );
				} );
			}
		};
		const initPrepopulatedFields = ( row ) => {
			row.find( '.prepopulated_field' ).each( function () {
				const field = $( this ),
					input = field.find( 'input, select, textarea' ),
					dependencyList = input.data( 'dependency_list' ) || [];
				const dependencies = [];
				dependencyList.forEach( ( fieldName ) => {
					dependencies.push( '#' + row.find( fieldName ).find( 'input, select, textarea' ).attr( 'id' ) );
				} );
				if ( dependencies.length ) {
					input.prepopulate( dependencies, input.attr( 'maxlength' ) );
				}
			} );
		};

		function togglePaymentDetails( selector ) {
			const tbody = selector.closest( 'tbody' );
			if ( !tbody ) {
				return;
			}

			const detailRows = tbody.querySelectorAll( '.expediture-details-row' );
			detailRows.forEach( function ( row ) {
				if ( selector.value === 'bank_transfer' ) {
					row.style.display = 'table-row';
				} else {
					row.style.display = 'none';
				}
			} );
		}

		function toggleAccountNumber( selector ) {
			const detailsRow = selector.closest( '.expediture-details-row' );
			if ( !detailsRow ) {
				return;
			}
			const accountNumberWrapper = detailsRow.querySelector( '.account-number-wrapper' );

			if ( selector.value ) {
				accountNumberWrapper.style.display = 'none';
				accountNumberWrapper.querySelector( 'input' ).value = '';
			} else {
				accountNumberWrapper.style.display = 'block';
			}
		}

		$( rows ).formset( {
			prefix: config.prefix,
			addText: config.addText,
			formCssClass: 'dynamic-' + config.prefix,
			deleteCssClass: 'inline-deletelink',
			addCssClass: config.addCssClass,
			deleteText: config.deleteText,
			emptyCssClass: 'empty-form',
			added: ( row ) => {
				row.find( '.field_DELETE .delete' ).empty();
				initPrepopulatedFields( row );
				reinitDateTimeShortCuts();
				updateSelectFilter();

				let deleteLink = row.children( 'a.inline-deletelink' );
				row.find( '.field_DELETE' ).append( deleteLink );

				let selector = row[ 0 ].querySelector( '.payment-type-selector' );
				if ( selector ) {
					togglePaymentDetails( selector );
				}
			}
		} );

		$( rows ).each( function () {
			let row = $( this );
			let deleteLink = row.children( 'a.inline-deletelink' );

			if ( deleteLink.length > 0 ) {
				if ( !row.hasClass( 'is-locked-row' ) && !row.hasClass( 'is-cofinancing-row' ) ) {
					row.find( '.field_DELETE' ).append( deleteLink );
				} else {
					deleteLink.remove();
				}
			}
		} );

		document.querySelectorAll( '.payment-type-selector' ).forEach( function ( el ) {
			togglePaymentDetails( el );
		} );

		document.querySelectorAll( '.saved-account-selector' ).forEach( function ( el ) {
			toggleAccountNumber( el );
		} );

		document.getElementById( config.prefix + '-group' ).addEventListener( 'change', function ( e ) {
			if ( e.target && e.target.classList.contains( 'payment-type-selector' ) ) {
				togglePaymentDetails( e.target );

				if ( e.target.value !== 'bank_transfer' ) {
					const tbody = e.target.closest( 'tbody' );
					const detailRows = tbody.querySelectorAll( '.expediture-details-row' );
					detailRows.forEach( function ( row ) {
						const inputs = row.querySelectorAll( 'input[type="text"], select:not(.payment-type-selector)' );
						inputs.forEach( function ( input ) {
							input.value = '';
						} );
					} );
				}
			}
			if ( e.target && e.target.classList.contains( 'saved-account-selector' ) ) {
				toggleAccountNumber( e.target );
			}
		} );
	} );
};
